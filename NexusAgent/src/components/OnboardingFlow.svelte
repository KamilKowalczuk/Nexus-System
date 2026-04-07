<script lang="ts">
  interface Props {
    token: string;
  }
  let { token }: Props = $props();

  // ─── STAN GLOBALNY ────────────────────────────────────────────────────────
  type Stage =
    | "loading"
    | "invalid"
    | "used"
    | "otp-email"
    | "otp-verify"
    | "brief"
    | "success";
  let stage = $state<Stage>("loading");
  let errorMsg = $state("");

  // Dane zamówienia
  let orderId = $state("");
  let customerEmail = $state("");
  let dailyLimit = $state(20);
  let monthlyAmount = $state(1999);
  let briefId = $state<string | null>(null);
  let mode = $state<"onboarding" | "edit">("onboarding");

  // OTP
  let emailInput = $state("");
  let otpInput = $state("");
  let otpSending = $state(false);
  let otpVerifying = $state(false);

  // Brief
  let submitting = $state(false);
  let brief = $state({
    companyName: "",
    industry: "",
    senderName: "",
    websiteUrl: "",
    actionMode: "save_to_drafts",
    campaignGoal: "",
    valueProposition: "",
    idealCustomerProfile: "",
    toneOfVoice: "professional",
    negativeConstraints: "",
    caseStudies: "",
    signatureHtml: "",
    autoGenerateSignature: true,
    warmupStrategy: true,
    authMethod: "nexus_lookalike_domain",
    requestedDomain: "",
    imapHost: "",
    imapPort: "993",
    imapUser: "",
    imapPassword: "",
    oauthProvider: "",
    oauthEmail: "",
    oauthRefreshToken: "",
  });

  // ─── OAUTH HANDLERS ──────────────────────────────────────────────────────
  let authPopup = $state<Window | null>(null);
  let authListenerAdded = false;
  let oauthErrorMsg = $state("");

  function openOAuthPopup(provider: string) {
    if (authPopup && !authPopup.closed) {
      authPopup.focus();
      return;
    }

    if (!authListenerAdded) {
      window.addEventListener("message", handleOAuthMessage);
      authListenerAdded = true;
    }

    const width = 500;
    const height = 650;
    const left = window.screenX + (window.outerWidth - width) / 2;
    const top = window.screenY + (window.outerHeight - height) / 2;

    authPopup = window.open(
      `/api/oauth/init?provider=${provider}`,
      "NexusOAuth",
      `width=${width},height=${height},left=${left},top=${top},status=yes,scrollbars=yes`
    );
  }

  function handleOAuthMessage(event: MessageEvent) {
    // SECURITY: weryfikacja źródła komunikatu (CORS protection)
    if (event.origin !== window.location.origin) return;

    const data = event.data;
    if (data && data.type === "OAUTH_SUCCESS") {
      brief.oauthProvider = data.provider;
      brief.oauthEmail = data.email;
      brief.oauthRefreshToken = data.encryptedToken;
      oauthErrorMsg = "";
    } else if (data && data.type === "OAUTH_ERROR") {
      oauthErrorMsg = data.message || "Błąd autoryzacji z zewnętrznym dostawcą.";
    }
  }

  // ─── INICJALIZACJA – weryfikacja tokenu ──────────────────────────────────
  $effect(() => {
    if (!token) {
      stage = "invalid";
      errorMsg = "Brak tokenu w URL.";
      return;
    }

    fetch(`/api/onboarding/verify-token?token=${encodeURIComponent(token)}`)
      .then((r) => r.json())
      .then((data) => {
        if (!data.valid) {
          if (data.error?.includes("już wykorzystany")) {
            stage = "used";
          } else {
            stage = "invalid";
            errorMsg = data.error || "Nieprawidłowy link.";
          }
          return;
        }
        orderId = data.orderId;
        customerEmail = data.customerEmail;
        dailyLimit = data.dailyLimit;
        monthlyAmount = data.monthlyAmount;
        // emailInput pozostaje pusty - wymóg zabezpieczenia, klient wpisuje go sam
        mode = data.mode === "edit" ? "edit" : "onboarding";

        stage = "otp-email";
      })
      .catch(() => {
        stage = "invalid";
        errorMsg = "Błąd połączenia z serwerem.";
      });
  });

  // ─── OTP – wyślij kod ────────────────────────────────────────────────────
  async function sendOtp() {
    otpSending = true;
    errorMsg = "";
    try {
      const res = await fetch("/api/onboarding/send-otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, email: emailInput, mode }),
      });
      const data = await res.json();
      if (!res.ok) {
        errorMsg = data.error || "Błąd wysyłki OTP.";
        return;
      }
      stage = "otp-verify";
    } catch {
      errorMsg = "Błąd połączenia.";
    } finally {
      otpSending = false;
    }
  }

  // ─── OTP – weryfikuj kod ─────────────────────────────────────────────────
  async function verifyOtp() {
    otpVerifying = true;
    errorMsg = "";
    try {
      const res = await fetch("/api/onboarding/verify-otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, otp: otpInput }),
      });
      const data = await res.json();

      if (!res.ok) {
        errorMsg = data.error || "Błąd weryfikacji.";
        return;
      }

      orderId = data.orderId;
      mode = data.mode === "edit" ? "edit" : "onboarding";

      // Przypisanie obiektu Brief dla formularza, jeśli backend zwrócił je jako odpowiedź OTP.
      if (mode === "edit" && data.brief && typeof data.brief === "object") {
        briefId = data.briefId ?? data.brief?.id ?? null;
        const b = data.brief;
        brief = {
          companyName: b.companyName ?? "",
          industry: b.industry ?? "",
          senderName: b.senderName ?? "",
          websiteUrl: b.websiteUrl ?? "",
          actionMode: b.actionMode ?? "save_to_drafts",
          campaignGoal: b.campaignGoal ?? "",
          valueProposition: b.valueProposition ?? "",
          idealCustomerProfile: b.idealCustomerProfile ?? "",
          toneOfVoice: b.toneOfVoice ?? "professional",
          negativeConstraints: b.negativeConstraints ?? "",
          caseStudies: b.caseStudies ?? "",
          signatureHtml: b.signatureHtml ?? "",
          autoGenerateSignature: !!b.autoGenerateSignature,
          warmupStrategy: b.warmupStrategy !== false,
          authMethod: b.authMethod ?? "nexus_lookalike_domain",
          requestedDomain: b.requestedDomain ?? "",
          imapHost: b.imapHost ?? "",
          imapPort: b.imapPort ?? "993",
          imapUser: b.imapUser ?? "",
          imapPassword: "", // Nigdy nie prefilluj – hasło jest zawsze ukryte / KMS
          oauthProvider: b.oauthProvider ?? "",
          oauthEmail: b.oauthEmail ?? "",
          oauthRefreshToken: b.oauthRefreshToken ? "[ZASZYFROWANE PRZEZ GOOGLE KMS]" : "",
        };
      }

      stage = "brief";
    } catch {
      errorMsg = "Błąd połączenia.";
    } finally {
      otpVerifying = false;
    }
  }

  // ─── BRIEF – wyślij formularz ────────────────────────────────────────────
  async function submitBrief() {
    submitting = true;
    errorMsg = "";
    try {
      const res = await fetch("/api/onboarding/submit-brief", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          token,
          orderId,
          briefData: brief,
          briefId,
          mode,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        errorMsg = data.details
          ? `${data.error}: ${data.details}`
          : data.error || "Błąd zapisu.";
        return;
      }
      stage = "success";
    } catch {
      errorMsg = "Błąd połączenia.";
    } finally {
      submitting = false;
    }
  }

  // ─── HELPERS ─────────────────────────────────────────────────────────────
  const authOptions = [
    {
      value: "nexus_lookalike_domain",
      label: "NEXUS Infrastructure",
      desc: "Tworzymy dla Ciebie domenę lookalike (np. b2bTwojaFirma.pl). Konfigurujemy SPF, DKIM, DMARC. Zero pracy po Twojej stronie. Zalecane na start. Po wdrożeniu oczekuj wiadomości z danumi dostępowymi do skrzynki",
      icon: "rocket_launch",
    },
    {
      value: "oauth",
      label: "Google / Microsoft OAuth",
      desc: "Autoryzujesz swoje konto Google Workspace lub Microsoft 365 jednym kliknięciem. Agent wysyła z Twojej domeny. Wymaga zatwierdzenia w panelu Google/MS.",
      icon: "key",
    },
    {
      value: "imap_encrypted_vault",
      label: "IMAP Encrypted Vault",
      desc: "Podajesz dane własnego serwera IMAP. Hasło zostaje natychmiast zaszyfrowane przez Google Cloud KMS. Nawet my nie mamy do niego dostępu. Maksymalna kontrola.",
      icon: "shield_lock",
    },
  ];
</script>

<!-- ═══════════════ LOADING ═══════════════ -->
{#if stage === "loading"}
  <div class="max-w-xl w-full text-center">
    <div class="rounded-3xl p-px bg-linear-to-b from-primary/40 to-primary/5">
      <div
        class="bg-slate-950/60 backdrop-blur-3xl rounded-3xl p-16 flex flex-col items-center gap-4"
      >
        <span
          class="material-symbols-outlined text-5xl text-primary animate-spin"
          >sync</span
        >
        <p class="font-mono text-sm text-slate-400 uppercase tracking-widest">
          Weryfikacja linku...
        </p>
      </div>
    </div>
  </div>

  <!-- ═══════════════ INVALID TOKEN ═══════════════ -->
{:else if stage === "invalid"}
  <div class="max-w-xl w-full text-center">
    <div class="rounded-3xl p-px bg-linear-to-b from-red-500/40 to-red-900/10">
      <div class="bg-slate-950/60 backdrop-blur-3xl rounded-3xl p-12 md:p-16">
        <span class="material-symbols-outlined text-5xl text-red-400 mb-6 block"
          >link_off</span
        >
        <h1
          class="font-display text-3xl font-bold uppercase tracking-tighter text-white mb-4"
        >
          Ten link nie działa
        </h1>
        <p class="text-slate-400 text-sm mb-8">{errorMsg}</p>
        <a
          href="/"
          class="inline-flex items-center gap-2 border border-white/10 text-slate-400 font-mono text-[10px] uppercase tracking-widest px-8 py-4 rounded-full hover:border-primary/30 hover:text-primary transition-all"
        >
          <span class="material-symbols-outlined text-sm">arrow_back</span> Wróć na
          stronę główną
        </a>
      </div>
    </div>
  </div>

  <!-- ═══════════════ ALREADY USED (BURN AFTER READING) ═══════════════ -->
{:else if stage === "used"}
  <div class="max-w-xl w-full text-center">
    <div
      class="rounded-3xl p-px bg-linear-to-b from-green-500/30 to-green-900/5"
    >
      <div class="bg-slate-950/60 backdrop-blur-3xl rounded-3xl p-12 md:p-16">
        <span
          class="material-symbols-outlined text-5xl text-green-400 mb-6 block"
          >check_circle</span
        >
        <div
          class="inline-block px-4 py-1.5 bg-green-500/10 border border-green-500/30 rounded-full text-[10px] font-mono text-green-400 uppercase tracking-widest mb-6"
        >
          Gotowe
        </div>
        <h1
          class="font-display text-3xl font-bold uppercase tracking-tighter text-white mb-4"
        >
          Formularz już wypełniony
        </h1>
        <p class="text-slate-400 text-sm leading-relaxed mb-8">
          Ten jednorazowy link wygasł po pierwszym użyciu. Twój formularz jest
          już u nas. NEXUS startuje w ciągu <strong class="text-white"
            >24–48 godzin</strong
          > – nic więcej nie musisz robić.
        </p>
        <a
          href="/"
          class="inline-flex items-center gap-2 border border-white/10 text-slate-400 font-mono text-[10px] uppercase tracking-widest px-8 py-4 rounded-full hover:border-primary/30 hover:text-primary transition-all"
        >
          <span class="material-symbols-outlined text-sm">arrow_back</span> Wróć na
          stronę główną
        </a>
      </div>
    </div>
  </div>

  <!-- ═══════════════ ETAP 1A: PODAJ EMAIL ═══════════════ -->
{:else if stage === "otp-email"}
  <div class="max-w-lg w-full">
    <div class="rounded-3xl p-px bg-linear-to-b from-primary/50 to-primary/10">
      <div class="bg-slate-950/60 backdrop-blur-3xl rounded-3xl p-10">
        <!-- Progress -->
        <div class="flex items-center gap-3 mb-8">
          <div class="flex-1 h-1 rounded-full bg-primary/60"></div>
          <div class="flex-1 h-1 rounded-full bg-white/10"></div>
        </div>

        <div
          class="inline-block px-3 py-1 bg-primary/10 border border-primary/30 rounded-full text-[10px] font-mono text-primary uppercase tracking-widest mb-6"
        >
          Krok 1 z 2 · Weryfikacja
        </div>

        <h2
          class="font-display text-2xl font-bold uppercase tracking-tighter text-white mb-3"
        >
          Podaj adres e-mail wykorzystany w zamówieniu
        </h2>
        <p class="text-slate-400 text-sm mb-8 leading-relaxed">
          Wyślemy jednorazowy kod, żeby potwierdzić, że formularz wypełnia
          właściwa osoba.
        </p>

        <div class="space-y-4">
          <div>
            <label
              for="emailInput"
              class="block text-[11px] font-mono text-slate-300 uppercase tracking-widest mb-2 font-medium"
              >Adres e-mail</label
            >
            <input
              id="emailInput"
              type="email"
              bind:value={emailInput}
              class="w-full bg-white/10 border border-white/20 rounded-xl px-5 py-4 text-white font-mono text-base focus:outline-none focus:border-primary/50 focus:bg-white/15 transition-all placeholder:text-slate-400 disabled:opacity-50"
              placeholder="twoj@firma.pl"
              disabled={otpSending}
            />
          </div>

          {#if errorMsg}
            <p
              class="text-red-400 text-xs font-mono bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-3"
            >
              {errorMsg}
            </p>
          {/if}

          <button
            onclick={sendOtp}
            disabled={otpSending || !emailInput}
            class="w-full py-4 rounded-2xl font-display font-bold uppercase text-sm text-white transition-all duration-300 disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            style="background: linear-gradient(135deg, hsl(270,60%,45%), hsl(280,70%,55%)); box-shadow: 0 0 30px hsl(270,60%,30%);"
          >
            {#if otpSending}
              <span class="material-symbols-outlined animate-spin text-sm"
                >sync</span
              >
              Wysyłanie kodu...
            {:else}
              <span class="material-symbols-outlined text-sm">send</span>
              Wyślij kod
            {/if}
          </button>
        </div>

        <!-- Security badge -->
        <div
          class="mt-6 flex items-center gap-2 text-xs text-slate-600 font-mono"
        >
          <span class="material-symbols-outlined text-sm text-slate-600"
            >shield</span
          >
          Kod ważny 10 minut · Twoje dane trafiają tylko do nas
        </div>
      </div>
    </div>
  </div>

  <!-- ═══════════════ ETAP 1B: WPISZ KOD OTP ═══════════════ -->
{:else if stage === "otp-verify"}
  <div class="max-w-lg w-full">
    <div class="rounded-3xl p-px bg-linear-to-b from-primary/50 to-primary/10">
      <div class="bg-slate-950/60 backdrop-blur-3xl rounded-3xl p-10">
        <!-- Progress -->
        <div class="flex items-center gap-3 mb-8">
          <div class="flex-1 h-1 rounded-full bg-primary/60"></div>
          <div class="flex-1 h-1 rounded-full bg-white/10"></div>
        </div>

        <div
          class="inline-block px-3 py-1 bg-primary/10 border border-primary/30 rounded-full text-[10px] font-mono text-primary uppercase tracking-widest mb-6"
        >
          Krok 1 z 2 · Weryfikacja
        </div>

        <h2
          class="font-display text-2xl font-bold uppercase tracking-tighter text-white mb-3"
        >
          Wpisz kod z maila
        </h2>
        <p class="text-slate-400 text-sm mb-8">
          Wysłaliśmy 6-cyfrowy kod na <strong class="text-white"
            >{emailInput}</strong
          >. Sprawdź też folder spam.
        </p>

        <div class="space-y-4">
          <div>
            <label
              for="otpInput"
              class="block text-[11px] font-mono text-slate-300 uppercase tracking-widest mb-2 font-medium"
              >Kod OTP (6 cyfr)</label
            >
            <input
              id="otpInput"
              type="text"
              bind:value={otpInput}
              maxlength={6}
              class="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-4 text-white font-mono text-2xl text-center tracking-[0.5em] focus:outline-none focus:border-primary/50 transition-colors"
              placeholder="000000"
              disabled={otpVerifying}
            />
          </div>

          {#if errorMsg}
            <p
              class="text-red-400 text-xs font-mono bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-3"
            >
              {errorMsg}
            </p>
          {/if}

          <button
            onclick={verifyOtp}
            disabled={otpVerifying || otpInput.length !== 6}
            class="w-full py-4 rounded-2xl font-display font-bold uppercase text-sm text-white transition-all duration-300 disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            style="background: linear-gradient(135deg, hsl(270,60%,45%), hsl(280,70%,55%)); box-shadow: 0 0 30px hsl(270,60%,30%);"
          >
            {#if otpVerifying}
              <span class="material-symbols-outlined animate-spin text-sm"
                >sync</span
              >
              Weryfikacja...
            {:else}
              <span class="material-symbols-outlined text-sm">verified</span>
              Potwierdź i przejdź dalej
            {/if}
          </button>

          <button
            onclick={() => {
              stage = "otp-email";
              errorMsg = "";
              otpInput = "";
            }}
            class="w-full py-3 text-slate-500 font-mono text-xs uppercase tracking-widest hover:text-slate-300 transition-colors"
          >
            ← Zmień adres
          </button>
        </div>
      </div>
    </div>
  </div>

  <!-- ═══════════════ ETAP 2: BRIEF WDROŻENIOWY ═══════════════ -->
{:else if stage === "brief"}
  <div class="max-w-2xl w-full">
    <!-- Progress -->
    <div class="flex items-center gap-3 mb-6">
      <div class="flex-1 h-1 rounded-full bg-primary/60"></div>
      <div class="flex-1 h-1 rounded-full bg-primary/60"></div>
    </div>

    <div
      class="inline-block px-3 py-1 bg-primary/10 border border-primary/30 rounded-full text-[10px] font-mono text-primary uppercase tracking-widest mb-6"
    >
      Krok 2 z 2 · Konfiguracja
    </div>

    <h2
      class="font-display text-3xl font-bold uppercase tracking-tighter text-white mb-2"
    >
      Powiedz nam o sobie i swoich klientach
    </h2>
    <p class="text-slate-400 text-sm mb-8">
      To jedyne 15 minut, które od Ciebie potrzebujemy. Na tej podstawie NEXUS
      będzie pisał wiadomości w Twoim imieniu.
    </p>

    <form
      onsubmit={(e) => {
        e.preventDefault();
        submitBrief();
      }}
    >
      <div class="space-y-6">
        <!-- DANE OGÓLNE -->
        <div class="rounded-2xl p-px bg-linear-to-b from-white/10 to-white/5">
          <div class="bg-slate-900/40 backdrop-blur-xl rounded-2xl p-6">
            <h3
              class="font-mono text-[10px] uppercase tracking-widest text-primary mb-5"
            >
              01 · Twoja firma
            </h3>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label
                  for="companyName"
                  class="block text-[11px] font-mono text-slate-300 uppercase tracking-widest mb-2 font-medium"
                  >Nazwa Firmy *</label
                >
                <input
                  id="companyName"
                  type="text"
                  bind:value={brief.companyName}
                  required
                  class="input-field"
                  placeholder="Nexus Systems sp. z o.o."
                />
              </div>
              <div>
                <label
                  for="industry"
                  class="block text-[11px] font-mono text-slate-300 uppercase tracking-widest mb-2 font-medium"
                  >Branża *</label
                >
                <input
                  id="industry"
                  type="text"
                  bind:value={brief.industry}
                  required
                  class="input-field"
                  placeholder="Software House / SaaS / Fintech..."
                />
              </div>
              <div>
                <label
                  for="senderName"
                  class="block text-[11px] font-mono text-slate-300 uppercase tracking-widest mb-2 font-medium"
                  >Imię i Nazwisko Nadawcy *</label
                >
                <input
                  id="senderName"
                  type="text"
                  bind:value={brief.senderName}
                  required
                  class="input-field"
                  placeholder="Jan Kowalski"
                />
              </div>
              <div>
                <label
                  for="websiteUrl"
                  class="block text-[11px] font-mono text-slate-300 uppercase tracking-widest mb-2 font-medium"
                  >Strona WWW</label
                >
                <input
                  id="websiteUrl"
                  type="url"
                  bind:value={brief.websiteUrl}
                  class="input-field"
                  placeholder="https://twojastrona.pl"
                />
              </div>
            </div>
          </div>
        </div>

        <!-- USTAWIENIA KAMPANII -->
        <div class="rounded-2xl p-px bg-linear-to-b from-white/10 to-white/5">
          <div class="bg-slate-900/40 backdrop-blur-xl rounded-2xl p-6">
            <h3
              class="font-mono text-[10px] uppercase tracking-widest text-primary mb-5"
            >
              02 · Jak mamy działać
            </h3>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
              {#each [{ value: "save_to_drafts", label: "Sprawdzaj przed wysyłką", desc: "Każda wiadomość trafia najpierw do Twoich roboczych. Przeglądasz i wysyłasz. Dobry start dla nowych kampanii." }, { value: "auto_send", label: "Wysyłaj automatycznie", desc: "NEXUS wysyła bez Twojego udziału. Wybierz po tym, jak sprawdzisz jakość pierwszej serii wiadomości." }] as mode}
                <button
                  type="button"
                  onclick={() => (brief.actionMode = mode.value)}
                  class="text-left p-4 rounded-xl border transition-all duration-200 {brief.actionMode ===
                  mode.value
                    ? 'border-primary/50 bg-primary/10'
                    : 'border-white/10 bg-white/3 hover:border-white/20'}"
                >
                  <div class="font-display font-bold text-sm text-white mb-1">
                    {mode.label}
                  </div>
                  <div class="text-slate-500 text-xs leading-relaxed">
                    {mode.desc}
                  </div>
                </button>
              {/each}
            </div>
          </div>
        </div>

        <!-- MÓZG AI -->
        <div class="rounded-2xl p-px bg-linear-to-b from-white/10 to-white/5">
          <div class="bg-slate-900/40 backdrop-blur-xl rounded-2xl p-6">
            <h3
              class="font-mono text-[10px] uppercase tracking-widest text-primary mb-5"
            >
              03 · Kto jest Twoim klientem
            </h3>
            <div class="space-y-4">
              <div>
                <label
                  for="campaignGoal"
                  class="block text-[11px] font-mono text-slate-300 uppercase tracking-widest mb-2 font-medium"
                  >Cel Kampanii *</label
                >
                <textarea
                  id="campaignGoal"
                  bind:value={brief.campaignGoal}
                  required
                  rows={2}
                  class="input-field resize-none"
                  placeholder="Np. Umówić 5 demo tygodniowo z CTOs firm 50-200 os. z branży SaaS w Polsce i DACH."
                ></textarea>
              </div>
              <div>
                <label
                  for="valueProposition"
                  class="block text-[11px] font-mono text-slate-300 uppercase tracking-widest mb-2 font-medium"
                  >Propozycja Wartości *</label
                >
                <textarea
                  id="valueProposition"
                  bind:value={brief.valueProposition}
                  required
                  rows={2}
                  class="input-field resize-none"
                  placeholder="Dlaczego klient ma odpowiedzieć? Jaki problem rozwiązujesz? (1-2 zdania)"
                ></textarea>
              </div>
              <div>
                <label
                  for="idealCustomerProfile"
                  class="block text-[11px] font-mono text-slate-300 uppercase tracking-widest mb-2 font-medium"
                  >Idealny Profil Klienta (ICP) *</label
                >
                <textarea
                  id="idealCustomerProfile"
                  bind:value={brief.idealCustomerProfile}
                  required
                  rows={2}
                  class="input-field resize-none"
                  placeholder="Branża, wielkość firmy, kraj, stanowisko decydenta, inne kryteria..."
                ></textarea>
              </div>
              <div>
                <label
                  for="toneOfVoice"
                  class="block text-[11px] font-mono text-slate-300 uppercase tracking-widest mb-2 font-medium"
                  >Ton Głosu</label
                >
                <select
                  id="toneOfVoice"
                  bind:value={brief.toneOfVoice}
                  class="input-field"
                >
                  <option value="formal">Formalny / Korporacyjny</option>
                  <option value="professional"
                    >Profesjonalny / Partnerski</option
                  >
                  <option value="direct">Bezpośredni / Konkretny</option>
                  <option value="technical">Techniczny / Ekspercki</option>
                </select>
              </div>
              <div>
                <label
                  for="negativeConstraints"
                  class="block text-[11px] font-mono text-slate-300 uppercase tracking-widest mb-2 font-medium"
                  >Czego NEXUS NIE może robić</label
                >
                <textarea
                  id="negativeConstraints"
                  bind:value={brief.negativeConstraints}
                  rows={2}
                  class="input-field resize-none"
                  placeholder="Np. Nie wspominaj o cenie. Nie pisz do firm poniżej 10 osób. Nie wymieniaj konkurencji X."
                ></textarea>
              </div>
              <div>
                <label
                  for="caseStudies"
                  class="block text-[11px] font-mono text-slate-300 uppercase tracking-widest mb-2 font-medium"
                  >Case Studies / Dowody Społeczne</label
                >
                <textarea
                  id="caseStudies"
                  bind:value={brief.caseStudies}
                  rows={2}
                  class="input-field resize-none"
                  placeholder="Krótkie opisy sukcesów lub linki. Agent będzie się na nie powoływać w mailach."
                ></textarea>
              </div>
            </div>
          </div>
        </div>

        <!-- METODA AUTH -->
        <div class="rounded-2xl p-px bg-linear-to-b from-white/10 to-white/5">
          <div class="bg-slate-900/40 backdrop-blur-xl rounded-2xl p-6">
            <h3
              class="font-mono text-[10px] uppercase tracking-widest text-primary mb-2"
            >
              04 · Skąd będziemy pisać *
            </h3>
            <p class="text-slate-500 text-xs mb-5">
              Z jakiego adresu mamy wysyłać wiadomości w Twoim imieniu?
            </p>

            <div class="space-y-3 mb-6">
              {#each authOptions as opt}
                <button
                  type="button"
                  onclick={() => (brief.authMethod = opt.value)}
                  class="w-full text-left p-4 rounded-xl border transition-all duration-200 {brief.authMethod ===
                  opt.value
                    ? 'border-primary/50 bg-primary/10'
                    : 'border-white/10 bg-white/3 hover:border-white/20'}"
                >
                  <div class="flex items-center gap-3 mb-2">
                    <span
                      class="material-symbols-outlined text-lg {brief.authMethod ===
                      opt.value
                        ? 'text-primary'
                        : 'text-slate-500'}">{opt.icon}</span
                    >
                    <span class="font-display font-bold text-sm text-white"
                      >{opt.label}</span
                    >
                    {#if opt.value === "nexus_lookalike_domain"}
                      <span
                        class="ml-auto text-[9px] font-mono text-green-400 border border-green-500/30 bg-green-500/10 px-2 py-0.5 rounded-full"
                        >Zalecane</span
                      >
                    {/if}
                  </div>
                  <p class="text-slate-500 text-xs leading-relaxed pl-8">
                    {opt.desc}
                  </p>
                </button>
              {/each}
            </div>

            <!-- Dodatkowe pola dla nexus_lookalike_domain -->
            {#if brief.authMethod === "nexus_lookalike_domain"}
              <div>
                <label
                  for="requestedDomain"
                  class="block text-[11px] font-mono text-slate-300 uppercase tracking-widest mb-2 font-medium"
                  >Żądana Domena (opcjonalne)</label
                >
                <input
                  id="requestedDomain"
                  type="text"
                  bind:value={brief.requestedDomain}
                  class="input-field"
                  placeholder="b2bTwojaFirma.pl (propozycja – finalny wybór po naszej analizie)"
                />
              </div>
            {/if}

            <!-- Dodatkowe pola dla OAuth -->
            {#if brief.authMethod === "oauth"}
              <div class="space-y-4 p-5 rounded-xl bg-blue-500/5 border border-blue-500/20 text-center">
                {#if brief.oauthRefreshToken}
                  <div class="flex flex-col items-center gap-3">
                    <div class="size-12 rounded-full bg-green-500/10 flex items-center justify-center border border-green-500/30">
                      <span class="material-symbols-outlined text-green-400 text-2xl">check_circle</span>
                    </div>
                    <div class="text-sm text-slate-300 font-medium tracking-wide">
                      Konto autoryzowane pomyślnie
                    </div>
                    <div class="text-[11px] font-mono text-primary bg-primary/10 px-3 py-1 rounded-full border border-primary/20">
                      {brief.oauthEmail}
                    </div>
                    <button type="button" onclick={() => { brief.oauthRefreshToken = ''; brief.oauthEmail = ''; brief.oauthProvider = ''; }} class="text-[10px] font-mono uppercase text-slate-500 hover:text-red-400 transition-colors mt-2 underline underline-offset-4 decoration-slate-700">
                      Odłącz i zmień konto
                    </button>
                  </div>
                {:else}
                  <div class="text-xs text-slate-400 mb-4">
                    Wybierz dostawcę, aby połączyć bezpiecznie konto pocztowe:
                  </div>
                  
                  {#if oauthErrorMsg}
                    <div class="text-[11px] text-red-400 font-mono mb-4 bg-red-400/10 border border-red-400/20 py-2 px-3 rounded-lg inline-block">
                      {oauthErrorMsg}
                    </div>
                  {/if}

                  <div class="flex flex-col sm:flex-row justify-center gap-3 max-w-sm mx-auto">
                    <button type="button" onclick={() => openOAuthPopup('google')} class="flex-1 flex items-center justify-center gap-2 bg-white text-slate-900 rounded-xl py-3 px-4 hover:bg-slate-200 transition-colors shadow-lg">
                       <img src="https://www.google.com/favicon.ico" alt="Google" class="w-4 h-4" />
                       <span class="text-xs font-bold font-sans">Google</span>
                    </button>
                    <button type="button" onclick={() => openOAuthPopup('microsoft')} class="flex-1 flex items-center justify-center gap-2 bg-[#2F2F2F] text-white border border-white/10 rounded-xl py-3 px-4 hover:bg-[#3f3f3f] transition-colors shadow-lg">
                       <svg class="w-4 h-4" viewBox="0 0 21 21"><rect x="1" y="1" width="9" height="9" fill="#f25022"/><rect x="11" y="1" width="9" height="9" fill="#7fba00"/><rect x="1" y="11" width="9" height="9" fill="#00a4ef"/><rect x="11" y="11" width="9" height="9" fill="#ffb900"/></svg>
                       <span class="text-xs font-bold font-sans">Microsoft</span>
                    </button>
                  </div>
                  <div class="mt-5 flex items-start gap-2 text-left bg-slate-900/50 p-3 rounded-lg border border-white/5">
                    <span class="material-symbols-outlined text-slate-500 text-sm mt-0.5">shield_lock</span>
                    <span class="text-[10px] text-slate-500 leading-tight">
                      Autoryzacja odbywa się bezpośrednio u dostawcy. Twój token dostępowy jest chroniony asymetrycznie przez wbudowany Vault Google Cloud KMS (zgodność z FIPS 140-2).
                    </span>
                  </div>
                {/if}
              </div>
            {/if}

            <!-- Dodatkowe pola dla IMAP -->
            {#if brief.authMethod === "imap_encrypted_vault"}
              <div
                class="space-y-3 p-4 rounded-xl bg-purple-500/5 border border-purple-500/20"
              >
                <div
                  class="flex items-center gap-2 text-[10px] font-mono text-purple-400 uppercase tracking-widest"
                >
                  <span class="material-symbols-outlined text-sm">lock</span>
                  Hasło jest szyfrowane natychmiast przy zapisie. Nikt – łącznie z
                  nami – nie ma do niego dostępu.
                </div>
                <div class="grid grid-cols-2 gap-3">
                  <div>
                    <label
                      for="imapHost"
                      class="block text-[11px] font-mono text-slate-300 uppercase tracking-widest mb-2 font-medium"
                      >IMAP Host</label
                    >
                    <input
                      id="imapHost"
                      type="text"
                      bind:value={brief.imapHost}
                      class="input-field"
                      placeholder="mail.firma.pl"
                    />
                  </div>
                  <div>
                    <label
                      for="imapPort"
                      class="block text-[11px] font-mono text-slate-300 uppercase tracking-widest mb-2 font-medium"
                      >Port</label
                    >
                    <input
                      id="imapPort"
                      type="text"
                      bind:value={brief.imapPort}
                      class="input-field"
                      placeholder="993"
                    />
                  </div>
                </div>
                <div>
                  <label
                    for="imapUser"
                    class="block text-[11px] font-mono text-slate-300 uppercase tracking-widest mb-2 font-medium"
                    >Email / Login IMAP</label
                  >
                  <input
                    id="imapUser"
                    type="text"
                    bind:value={brief.imapUser}
                    class="input-field"
                    placeholder="jan@firma.pl"
                  />
                </div>
                <div>
                  <label
                    for="imapPassword"
                    class="block text-[11px] font-mono text-slate-300 uppercase tracking-widest mb-2 font-medium"
                    >Hasło IMAP</label
                  >
                  <input
                    id="imapPassword"
                    type="password"
                    bind:value={brief.imapPassword}
                    class="input-field"
                    placeholder="••••••••••"
                  />
                  <p class="text-slate-600 text-[10px] font-mono mt-1.5">
                    {#if mode === "edit"}
                      🔐 Puste = zachowaj obecne hasło. Wpisanie nowego nadpisze
                      je (szyfrowanie GCP KMS).
                    {:else}
                      🔐 Zaszyfrowane natychmiast przy zapisie przez GCP KMS
                    {/if}
                  </p>
                </div>
              </div>
            {/if}
          </div>
        </div>

        <!-- USTAWIENIA DODATKOWE -->
        <div class="rounded-2xl p-px bg-linear-to-b from-white/10 to-white/5">
          <div class="bg-slate-900/40 backdrop-blur-xl rounded-2xl p-6">
            <h3
              class="font-mono text-[10px] uppercase tracking-widest text-primary mb-5"
            >
              05 · Ustawienia
            </h3>
            <div class="space-y-3">
              <label
                class="flex items-center gap-3 cursor-pointer p-3 rounded-xl hover:bg-white/3 transition-colors"
              >
                <input
                  type="checkbox"
                  bind:checked={brief.warmupStrategy}
                  class="w-4 h-4 accent-primary"
                />
                <div>
                  <div class="text-white text-sm font-display font-bold">
                    Zacznij powoli
                  </div>
                  <div class="text-slate-500 text-xs">
                    Przez pierwsze 2 tygodnie zwiększamy tempo stopniowo. To
                    chroni nową domenę przed trafieniem do spamu i daje lepsze
                    wyniki długoterminowo.
                  </div>
                </div>
              </label>
              <label
                class="flex items-center gap-3 cursor-pointer p-3 rounded-xl hover:bg-white/3 transition-colors"
              >
                <input
                  type="checkbox"
                  bind:checked={brief.autoGenerateSignature}
                  class="w-4 h-4 accent-primary"
                />
                <div>
                  <div class="text-white text-sm font-display font-bold">
                    Zrób mi stopkę
                  </div>
                  <div class="text-slate-500 text-xs">
                    NEXUS stworzy profesjonalną stopkę maila na podstawie
                    danych, które podałeś powyżej.
                  </div>
                </div>
              </label>
            </div>
          </div>
        </div>

        {#if errorMsg}
          <div
            class="text-red-400 text-sm font-mono bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-3"
          >
            {errorMsg}
          </div>
        {/if}

        <!-- SUBMIT -->
        <button
          type="submit"
          disabled={submitting}
          class="w-full py-5 rounded-2xl font-display font-bold uppercase text-white text-sm tracking-wider transition-all duration-300 disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-3"
          style="background: linear-gradient(135deg, hsl(270,60%,45%), hsl(280,70%,55%)); box-shadow: 0 0 40px hsl(270,60%,25%);"
        >
          {#if submitting}
            <span class="material-symbols-outlined animate-spin">sync</span>
            Zapisywanie i generowanie PDF...
          {:else if mode === "edit"}
            <span class="material-symbols-outlined">save</span>
            Zapisz zmiany
          {:else}
            <span class="material-symbols-outlined">rocket_launch</span>
            Uruchom kampanię
          {/if}
        </button>

        <p
          class="text-center text-slate-600 text-[10px] font-mono uppercase tracking-widest"
        >
          Dostaniesz maila z potwierdzeniem i podsumowaniem w PDF · {#if mode === "edit"}Możesz
            edytować ten formularz wielokrotnie używając nowo wygenerowanych
            linków{:else}Link wygasa po użyciu{/if}
        </p>
      </div>
    </form>
  </div>

  <!-- ═══════════════ SUCCESS ═══════════════ -->
{:else if stage === "success"}
  <div class="max-w-xl w-full text-center">
    <div
      class="rounded-3xl p-px bg-linear-to-b from-green-500/50 to-green-900/10 mb-8"
    >
      <div class="bg-slate-950/60 backdrop-blur-3xl rounded-3xl p-12 md:p-16">
        <span class="relative flex h-8 w-8 mx-auto mb-8">
          <span
            class="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"
          ></span>
          <span
            class="relative inline-flex rounded-full h-8 w-8 bg-green-500 shadow-[0_0_24px_#22c55e]"
          ></span>
        </span>

        <div
          class="inline-block px-4 py-1.5 bg-green-500/10 border border-green-500/30 rounded-full text-[10px] font-mono text-green-400 uppercase tracking-widest mb-6"
        >
          Formularz przyjęty
        </div>

        <h1
          class="font-display text-3xl md:text-4xl font-bold uppercase tracking-tighter text-white mb-4"
        >
          Gotowe.<br />
          <span class="text-green-400">Teraz ruszamy.</span>
        </h1>

        <p class="text-slate-400 text-sm leading-relaxed mb-10">
          Mamy Twój formularz, spodziewaj się pliku PDF z podsumowaniem na
          swojej skrzynce e-mail. W ciągu <strong class="text-white"
            >24–48 godzin</strong
          > NEXUS zaczyna pisać do Twoich potencjalnych klientów.
        </p>

        <div class="space-y-3 text-left mb-10">
          {#each ["Przygotowanie listy firm i analizy (24–48h)", "Konfiguracja poczty i domeny", "Pierwsze wiadomości do potencjalnych klientów", "Raport z wynikami co 3 dni"] as step, i}
            <div class="flex items-center gap-4">
              <div
                class="size-6 rounded-full bg-green-500/10 border border-green-500/30 flex items-center justify-center shrink-0"
              >
                <span class="text-green-400 text-[10px] font-mono font-bold"
                  >{i + 1}</span
                >
              </div>
              <span class="text-slate-300 text-sm">{step}</span>
            </div>
          {/each}
        </div>

        <a
          href="/"
          class="inline-flex items-center gap-2 border border-white/10 text-slate-400 font-mono text-[10px] uppercase tracking-widest px-8 py-4 rounded-full hover:border-primary/30 hover:text-primary transition-all"
        >
          <span class="material-symbols-outlined text-sm">arrow_back</span>
          Wróć na stronę główną
        </a>
      </div>
    </div>
    <div class="font-mono text-[9px] text-slate-600 uppercase tracking-widest">
      STATUS: URUCHAMIANIE · NEXUS AGENT · FORMULARZ ZAPISANY ✓
    </div>
  </div>
{/if}

<style>
  :global(.input-field) {
    width: 100%;
    background: rgba(255, 255, 255, 0.08); /* 8% opacity */
    border: 1px solid rgba(255, 255, 255, 0.2);
    border-radius: 0.75rem;
    padding: 1rem 1.25rem;
    color: #fff;
    font-family: "Inter", monospace;
    font-size: 1rem;
    transition:
      border-color 0.2s,
      background-color 0.2s;
    outline: none;
  }
  :global(.input-field:focus) {
    border-color: rgba(168, 85, 247, 0.6);
    background: rgba(255, 255, 255, 0.12);
  }
  :global(.input-field::placeholder) {
    color: #94a3b8;
  }
  :global(select.input-field option) {
    background: #0a0a0f;
    color: #e2e8f0;
  }
</style>
