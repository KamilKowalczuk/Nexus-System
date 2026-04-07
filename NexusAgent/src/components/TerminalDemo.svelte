<script lang="ts">
  import { Completion } from "@ai-sdk/svelte";

  const {
    badge = "SYMULACJA TERMINALA – REALNE DANE",
    headline = "Sprawdź, ile pieniędzy zostawiasz dziś na stole.",
    inputLabelUrl = "URL firmy, której leady chcesz przejąć",
    inputLabelIndustry = "Branża lub nisza (opcjonalnie)",
  } = $props<{
    badge?: string;
    headline?: string;
    inputLabelUrl?: string;
    inputLabelIndustry?: string;
  }>();

  let targetUrl = $state("");
  let industry = $state("");

  // Rate Limiting & Validation Logic
  const MAX_USAGE = 4;
  let usageCount = $state<number>(0);
  let isLocked = $state<boolean>(false);
  let isPageLoad = true; // flaga, żeby odróżnić odświeżenie strony od kliknięcia

  // Initialize from localStorage on mount (check for browser environment)
  $effect(() => {
    if (typeof window !== "undefined") {
      // 1. Optimistic UI from localStorage
      const stored = localStorage.getItem("nexus_agent_demo_limits");
      if (stored) {
        const storedCount = parseInt(stored, 10);
        usageCount = storedCount;
        // Natychmiast pokaż overlay jeśli localStorage mówi że limit wyczerpany
        if (storedCount >= MAX_USAGE) {
          isLocked = true;
        }
      }

      // 2. Fetch real status from server ONLY on initial mount
      const hasCheckedServer = sessionStorage.getItem("nexus_demo_checked");
      if (!hasCheckedServer || usageCount >= MAX_USAGE) {
        fetch("/api/demo-status")
          .then((res) => res.json())
          .then((data) => {
            if (data && typeof data.usageCount === "number") {
              // Serwer nadpisuje TYLKO jeśli ma wyższą wartość niż local
              // LUB jeśli serwer mówi, że IP jest zablokowane (admin mógł zmienić)
              if (data.isLocked) {
                isLocked = true;
                usageCount = Math.max(usageCount, data.usageCount);
              } else if (data.usageCount > usageCount) {
                usageCount = data.usageCount;
                // Jeśli serwer mówi >= MAX_USAGE, zablokuj natychmiast
                if (data.usageCount >= MAX_USAGE) {
                  isLocked = true;
                }
              } else if (usageCount >= MAX_USAGE) {
                // localStorage mówi >= MAX_USAGE, serwer nie zaprzecza
                isLocked = true;
              } else {
                isLocked = false;
              }
              localStorage.setItem(
                "nexus_agent_demo_limits",
                usageCount.toString(),
              );
              sessionStorage.setItem("nexus_demo_checked", "true");
            }
          })
          .catch((err) => console.error("Failed to fetch demo status:", err))
          .finally(() => {
            isPageLoad = false;
          });
      } else {
        // Nawet jeśli nie odpytujemy serwera, sprawdź localStorage
        if (usageCount >= MAX_USAGE) {
          isLocked = true;
        }
        isPageLoad = false;
      }
    }
  });

  // Osobny $effect: Jedyny mechanizm odpowiedzialny za opóźniony popup po 4. użyciu.
  // Odpala się TYLKO gdy usageCount zmieni się na >= MAX_USAGE i NIE jest to ładowanie strony.
  $effect(() => {
    if (usageCount >= MAX_USAGE && !isLocked && !isPageLoad) {
      const timer = setTimeout(() => {
        isLocked = true;
      }, 7000);

      return () => clearTimeout(timer);
    }
  });

  // URL Validator mapping HTTP/HTTPS optionally, demanding domain format
  const isValidUrl = () => {
    if (!targetUrl) return false;

    // Ulepszona walidacja URL z użyciem wbudowanego obiektu URL w JS
    try {
      // Jeśli użytkownik wpisał samą domenę (np. "firma.pl"), dodajemy protokół,
      // żeby konstruktor URL zadziałał poprawnie
      const urlToTest = targetUrl.startsWith("http")
        ? targetUrl
        : `https://${targetUrl}`;
      const parsedUrl = new URL(urlToTest);

      // Sprawdzamy czy domena ma kropkę i przynajmniej 2 znaki po kropce (np. .pl, .com)
      const domainParts = parsedUrl.hostname.split(".");
      if (domainParts.length < 2) return false;

      const tld = domainParts[domainParts.length - 1];
      if (tld.length < 2) return false;

      // Odrzucamy localhost i lokalne IP
      if (
        parsedUrl.hostname === "localhost" ||
        parsedUrl.hostname === "127.0.0.1"
      )
        return false;

      return true;
    } catch (e) {
      return false;
    }
  };

  let terminalLines = $state<string[]>([
    "nexus@agent:~$ system gotowy do pracy... każdy dzień bez wysyłki to utracony kapitał.",
  ]);

  // Używamy instancji wbudowanej w Runes The (Svelte 5 API z Vercela)
  const generator = new Completion({
    api: "/api/demo-attack",
    streamProtocol: "text",
    onFinish: async () => {
      terminalLines = [
        ...terminalLines,
        `[SYSTEM] Analiza zakończona. Cel znaleziony, draft gotowy do wysyłki.`,
      ];
      // Send metric to Payload CMS Dashboard
      try {
        await fetch(
          `${import.meta.env?.PUBLIC_PAYLOAD_URL || "http://localhost:3000"}/api/demo-usages`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              targetUrl,
              generatedSubject: generator.completion
                ? generator.completion.substring(0, 100)
                : "Brak",
            }),
          },
        );
      } catch (e) {
        console.error("Failed to log demo usage", e);
      }
    },
    onError: (err) => {
      // Sprawdzamy czy błąd to 429, 403 lub czy w treści błędu jest informacja o blokadzie
      if (
        err.message.includes("429") ||
        err.message.includes("Too Many Requests") ||
        err.message.includes("403") ||
        err.message.includes("IP is blocked")
      ) {
        // Ustawiamy na MAX_USAGE + 1, żeby UI wiedziało że koniec
        usageCount = MAX_USAGE + 1;
        localStorage.setItem("nexus_agent_demo_limits", usageCount.toString());
        sessionStorage.removeItem("nexus_demo_checked");

        terminalLines = [
          ...terminalLines,
          `[SYSTEM ALERT] LIMIT DEMO WYCZERPANY LUB DOSTĘP ZABLOKOWANY.`,
          `> Przeanalizowano 4 profile. Szacunkowy potencjał przychodu: 40 000 – 160 000 PLN.`,
          `> Dostęp do pełnej mocy obliczeniowej NEXUS został odłączony.`,
        ];

        isLocked = true;
      } else {
        // Revert optimistic update on error (tylko dla prawdziwych błędów, nie dla blokad)
        usageCount = Math.max(0, usageCount - 1);
        localStorage.setItem("nexus_agent_demo_limits", usageCount.toString());
        terminalLines = [...terminalLines, `[ERROR] API Error: ${err.message}`];
      }
    },
  });

  async function startAttack() {
    if (isLocked) return;

    if (!isValidUrl()) {
      terminalLines = [
        ...terminalLines,
        `[BŁĄD SYSTEMU] Nierozpoznany adres. Nie marnujemy wysyłek na przypadkowe URL-e.`,
      ];
      // Shake animation effect for invalid input
      const inputEl = document.getElementById("demo-url");
      if (inputEl) {
        inputEl.classList.add("animate-shake");
        setTimeout(() => inputEl.classList.remove("animate-shake"), 500);
      }
      return;
    }

    let domain = "";
    try {
      domain = new URL(
        targetUrl.startsWith("http") ? targetUrl : `https://${targetUrl}`,
      ).hostname;
    } catch (e) {
      domain = targetUrl;
    }

    // Increment usage (Optimistic UI)
    usageCount += 1;
    localStorage.setItem("nexus_agent_demo_limits", usageCount.toString());

    // Jeśli to jest 5 użycie (usageCount > 4), blokujemy natychmiast bez wysyłania do API.
    if (usageCount > MAX_USAGE) {
      // Wymuszamy wyczyszczenie sessionStorage, żeby przy następnym odświeżeniu zapytał serwer
      sessionStorage.removeItem("nexus_demo_checked");
      terminalLines = [
        ...terminalLines,
        `[SYSTEM ALERT] LIMIT DEMO WYCZERPANY.`,
        `> Przeanalizowano 4 profile. Szacunkowy potencjał przychodu: 40 000 – 160 000 PLN.`,
        `> Dostęp do pełnej mocy obliczeniowej NEXUS został odłączony.`,
        `> Każdy kolejny dzień bez systemowego outboundu powiększa tę lukę po stronie Twojej konkurencji.`,
      ];

      isLocked = true;
      return;
    }

    // Jeśli to jest 4 użycie (ostatnie), czyścimy sessionStorage, żeby przy odświeżeniu
    // skrypt na 100% zapytał serwera i dostał isBlocked: true
    if (usageCount === MAX_USAGE) {
      sessionStorage.removeItem("nexus_demo_checked");
    }

    terminalLines = [
      `nexus@agent:~$ analiza-rynku --cel=${domain} ${industry ? `--branza=${industry}` : ""} --gleboki-skan`,
      `[SYSTEM] Start analizy i przygotowania sekwencji cold mail...`,
      `[INFO] Identyfikacja decydentów i krytycznych danych biznesowych...`,
      `[INFO] Projektowanie wiadomości, która nie wygląda jak masowa kampania...`,
    ];

    try {
      // Płynne przewijanie do terminala na urządzeniach mobilnych (poniżej breakpointu lg)
      if (window.innerWidth < 1024) {
        const terminalElement = document.getElementById("terminal-view");
        if (terminalElement) {
          terminalElement.scrollIntoView({
            behavior: "smooth",
            block: "start",
          });
        }
      }

      // The options.body wasn't reacting appropriately in older `@ai-sdk/svelte` without passing payload directly,
      // so let's pass it via stringified options to complete.
      await generator.complete(targetUrl, {
        body: { url: targetUrl, industry: industry },
      });
    } catch (err) {
      terminalLines = [...terminalLines, `[ERROR] Wystąpił błąd: ${err}`];
    }
  }
</script>

<section
  class="relative z-20 max-w-7xl mx-auto px-8 py-32 w-full grid grid-cols-1 lg:grid-cols-2 gap-20 items-center"
  id="demo"
>
  <!-- Left side – Parameters -->
  <div class="fade-up relative z-20">
    <div
      class="inline-flex items-center gap-2 px-3 py-1 rounded-full mb-8 text-[10px] font-mono uppercase tracking-[0.2em] transition-colors duration-500 border-primary/20 bg-primary/5 text-primary"
    >
      {badge}
    </div>
    <h2
      class="font-display text-5xl font-bold uppercase tracking-tighter mb-8 leading-none"
    >
      {@html headline}
    </h2>
    <div class="space-y-8">
      <div class="space-y-2 relative pb-5">
        <label
          for="demo-url"
          class="font-mono text-[11px] uppercase text-slate-500 tracking-widest flex justify-between"
          ><span>{inputLabelUrl}</span>
          <span class={usageCount >= MAX_USAGE ? "text-amber-500" : ""}
            >DARMOWE: {Math.max(0, MAX_USAGE - usageCount)}</span
          >
        </label>
        <input
          id="demo-url"
          bind:value={targetUrl}
          class="w-full bg-black/40 border border-slate-800 rounded-xl p-5 font-mono text-primary focus:border-primary focus:ring-1 focus:ring-primary/20 outline-none transition-all duration-300 placeholder:text-slate-700 {targetUrl &&
          !isValidUrl()
            ? 'border-red-500/50 text-red-400 focus:border-red-500 focus:ring-red-500/20'
            : ''}"
          placeholder="https://competitor.pl"
          type="url"
          autocomplete="off"
          maxlength="100"
          disabled={generator.loading}
        />
        <div
          class="absolute bottom-0 left-0 text-red-400 text-[10px] font-mono uppercase tracking-widest transition-opacity duration-300 {targetUrl &&
          !isValidUrl()
            ? 'opacity-100'
            : 'opacity-0 pointer-events-none'}"
        >
          Wymagany poprawny adres domeny (np. firma.pl)
        </div>
      </div>
      <div class="space-y-2">
        <label
          for="demo-industry"
          class="font-mono text-[11px] uppercase text-slate-500 tracking-widest"
          >{inputLabelIndustry}</label
        >
        <input
          id="demo-industry"
          bind:value={industry}
          class="w-full bg-black/40 border border-slate-800 rounded-xl p-5 font-mono text-primary focus:border-primary focus:ring-1 focus:ring-primary/20 outline-none transition-all duration-300 placeholder:text-slate-700"
          placeholder="e.g. Fintech, Manufacturing"
          type="text"
          autocomplete="off"
          maxlength="100"
          disabled={generator.loading}
        />
      </div>
      <button
        onclick={startAttack}
        disabled={generator.loading ||
          !targetUrl ||
          isLocked ||
          !isValidUrl() ||
          usageCount >= MAX_USAGE}
        class="w-full font-display font-bold text-sm uppercase px-8 py-6 rounded-xl transition-all duration-300 disabled:opacity-30 disabled:cursor-not-allowed hover:scale-[1.02] flex items-center justify-center gap-4 bg-primary text-bg-dark neon-shadow-cyan hover:brightness-110"
      >
        {#if usageCount >= MAX_USAGE}
          LIMIT WYCZERPANY <span class="material-symbols-outlined">lock</span>
        {:else if generator.loading}
          System Pracuje... <span class="material-symbols-outlined animate-spin"
            >sync</span
          >
        {:else}
          Generuj wiadomość<span class="material-symbols-outlined">bolt</span>
        {/if}
      </button>
    </div>
  </div>

  <!-- Right side – Terminal -->
  <div
    id="terminal-view"
    class="glass rounded-2xl overflow-hidden border border-slate-800 shadow-2xl relative bg-black/80 fade-up transition-all duration-700 z-10"
    style="transition-delay: 200ms;"
  >
    <!-- Sweeping top-bar light -->
    <div class="absolute top-0 left-0 w-full h-px overflow-hidden">
      {#if generator.loading}
        <div
          class="w-[40%] h-full bg-primary/60"
          style="animation: sweep 2s ease-in-out infinite;"
        ></div>
      {/if}
    </div>

    <div
      class="bg-slate-900/60 px-6 py-4 flex items-center justify-between border-b border-white/5"
    >
      <div class="flex gap-2">
        <div
          class="size-3 rounded-full bg-red-500/30 hover:bg-red-500 transition-colors duration-300 cursor-pointer"
        ></div>
        <div
          class="size-3 rounded-full bg-yellow-500/30 hover:bg-yellow-500 transition-colors duration-300 cursor-pointer"
        ></div>
        <div
          class="size-3 rounded-full bg-green-500/30 hover:bg-green-500 transition-colors duration-300 cursor-pointer"
        ></div>
      </div>
      <div
        class="font-mono text-[10px] text-slate-500 tracking-widest uppercase auto-glitch"
      >
        NEXUS_SYSTEM_CONSOLE V3.1
      </div>
    </div>
    <div class="p-8 font-mono text-sm min-h-[500px] overflow-y-auto space-y-3">
      {#each terminalLines as line}
        <div
          class="text-xs {line.includes('nexus@')
            ? 'text-slate-100! text-sm!'
            : line.includes('[ERROR]') || line.includes('[BŁĄD SYSTEMU]')
              ? 'text-red-400!'
              : line.includes('[SYSTEM ALERT]') ||
                  line.includes('LIMIT OPERACYJNY WYCZERPANY') ||
                  line.includes('Szacowana wartość') ||
                  line.includes('Zdejmij ograniczenia') ||
                  line.includes(
                    'Dostęp do chmury obliczeniowej NEXUS odłączony.',
                  )
                ? 'text-amber-500! font-bold'
                : 'text-slate-500'} {line.includes('[SYSTEM]') ? 'italic' : ''}"
        >
          {line}
        </div>
      {/each}

      {#if generator.completion}
        <div class="text-primary text-xs font-bold mt-4">
          [SYSTEM] Wygenerowano spersonalizowany draft gotowy do wysyłki.
        </div>
        <div
          class="bg-white/5 p-6 rounded-xl border-l-2 border-primary/40 mt-6 space-y-3"
        >
          <div
            class="text-[10px] text-primary/50 uppercase font-bold tracking-widest"
          >
            Podgląd treści:
          </div>
          <div class="text-white/90 leading-relaxed italic whitespace-pre-wrap">
            {generator.completion}
          </div>
        </div>
      {/if}

      <div class="flex items-center gap-1 mt-6 {isLocked ? 'hidden' : ''}">
        <span class="text-primary">root@nexus:</span><span class="text-white"
          >_</span
        >
        <span class="glitch-caret blink"></span>
      </div>
    </div>
  </div>

  <!-- THE LOCKDOWN OVERLAY -->
  {#if isLocked}
    <div
      class="absolute inset-0 z-50 flex items-center justify-center p-8 transition-opacity duration-1000"
    >
      <!-- Glass backdrop over the entire section -->
      <div
        class="absolute inset-0 bg-black/60 backdrop-blur-md rounded-[3rem] border border-amber-500/20"
      ></div>

      <!-- CTA Content -->
      <div
        class="relative z-10 flex flex-col items-center justify-center text-center max-w-2xl mx-auto"
      >
        <div
          class="mb-6 size-20 rounded-full bg-amber-500/10 flex items-center justify-center border border-amber-500/30"
        >
          <span class="material-symbols-outlined text-amber-500 text-4xl"
            >lock</span
          >
        </div>

        <h3
          class="text-3xl font-display font-bold text-white mb-4 tracking-wide"
        >
          [ DOSTĘP OGRANICZONY: LIMIT ZAPYTAŃ OSIĄGNIĘTY ]
        </h3>

        <p
          class="text-slate-200 font-mono text-lg uppercase mb-6 leading-relaxed font-bold"
        >
          Widzisz tylko kilka przykładowych draftów pod własną stronę. Każdy
          kolejny klient, którego nie przepuścisz przez NEXUS, dostanie taką
          wiadomość od kogoś innego.
        </p>

        <p
          class="text-slate-400 font-mono text-sm uppercase mb-10 leading-relaxed max-w-lg"
        >
          Możesz zatrzymać się na wersji demo i dalej zgadywać, skąd wezmą się
          nowe zapytania, albo odblokować pełną wersję i zamienić te drafty w
          stały dopływ spotkań sprzedażowych.
        </p>

        <a
          href="#pricing"
          class="bg-amber-500 text-black font-display font-bold text-base uppercase px-12 py-5 rounded-xl hover:scale-105 transition-all duration-300 shadow-[0_0_40px_rgba(245,158,11,0.4)] hover:shadow-[0_0_60px_rgba(245,158,11,0.6)] flex items-center gap-3 w-full sm:w-auto justify-center"
        >
          AUTORYZUJ DOSTĘP PREMIUM <span class="material-symbols-outlined"
            >key</span
          >
        </a>
      </div>
    </div>
  {/if}
</section>

<style>
  @keyframes sweep {
    0% {
      transform: translateX(-100%);
    }
    50% {
      transform: translateX(350%);
    }
    100% {
      transform: translateX(-100%);
    }
  }
  .blink {
    animation: blink-anim 1s step-end infinite;
    display: inline-block;
    width: 0.6em;
    height: 1.2em;
    background-color: white;
    vertical-align: middle;
  }
  @keyframes blink-anim {
    0%,
    100% {
      opacity: 1;
    }
    50% {
      opacity: 0;
    }
  }
  .glass {
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
  }

  @keyframes shake {
    0%,
    100% {
      transform: translateX(0);
    }
    10%,
    30%,
    50%,
    70%,
    90% {
      transform: translateX(-5px);
    }
    20%,
    40%,
    60%,
    80% {
      transform: translateX(5px);
    }
  }

  :global(.animate-shake) {
    animation: shake 0.4s cubic-bezier(0.36, 0.07, 0.19, 0.97) both;
  }
</style>
