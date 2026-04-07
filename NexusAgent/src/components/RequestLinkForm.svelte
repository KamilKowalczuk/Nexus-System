<script lang="ts">
  let isOpen = $state(false);
  let email = $state("");
  let orderNumber = $state("");
  let status = $state<
    "idle" | "loading" | "success" | "not_found" | "rate_limit" | "error"
  >("idle");
  let rateLimitMinutes = $state(0);

  // Otwieranie modala przez zewnętrzny event (z linku w stopce)
  $effect(() => {
    const handleOpen = () => {
      isOpen = true;
    };
    document.addEventListener("open-brief-form", handleOpen);
    return () => document.removeEventListener("open-brief-form", handleOpen);
  });

  function close() {
    isOpen = false;
    status = "idle";
    email = "";
    orderNumber = "";
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === "Escape") close();
  }

  async function handleSubmit(e: SubmitEvent) {
    e.preventDefault();
    if (!email || !orderNumber) return;

    status = "loading";

    try {
      const res = await fetch("/api/onboarding/resend-from-website", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: email.trim(),
          orderNumber: orderNumber.trim().toUpperCase(),
        }),
      });

      const data = await res.json();

      if (res.status === 429) {
        rateLimitMinutes = data.resetInMinutes || 10;
        status = "rate_limit";
      } else if (res.ok && data.ok === false && data.state === "not_found") {
        status = "not_found";
      } else if (res.ok && data.ok !== false) {
        status = "success";
      } else {
        status = "error";
      }
    } catch {
      status = "error";
    }
  }
</script>

{#if isOpen}
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div
    class="fixed inset-0 z-9999 flex items-center justify-center p-4"
    onkeydown={handleKeydown}
  >
    <!-- Overlay -->
    <!-- svelte-ignore a11y_click_events_have_key_events -->
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div
      class="absolute inset-0 bg-black/80 backdrop-blur-sm"
      onclick={close}
    ></div>

    <!-- Modal -->
    <div class="relative z-10 w-full max-w-md">
      <div
        class="glass border border-white/10 rounded-2xl p-8"
        style="background: rgba(5,5,8,0.97);"
      >
        <!-- Header -->
        <div class="flex items-start justify-between mb-6">
          <div>
            <div
              class="text-[10px] font-mono text-cyan-400 uppercase tracking-widest mb-1"
            >
              Strefa Klienta NEXUS
            </div>
            <h2 class="text-xl font-black text-white uppercase tracking-tight">
              Edytuj / wyślij ponownie brief
            </h2>
          </div>
          <button
            onclick={close}
            class="text-slate-500 hover:text-white transition-colors ml-4 shrink-0"
            aria-label="Zamknij"
          >
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
              <path
                d="M15 5L5 15M5 5l10 10"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linecap="round"
              />
            </svg>
          </button>
        </div>

        {#if status === "success"}
          <!-- Stan: sukces -->
          <div class="text-center py-6">
            <div
              class="w-14 h-14 rounded-full bg-green-500/10 border border-green-500/30 flex items-center justify-center mx-auto mb-4"
            >
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                <path
                  d="M5 13l4 4L19 7"
                  stroke="#22c55e"
                  stroke-width="2"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />
              </svg>
            </div>
            <p class="text-white font-bold text-lg mb-2">Link wysłany!</p>
            <p class="text-slate-400 text-sm">
              Jeśli dane są poprawne, link zostanie wysłany na Twój adres email.
              Sprawdź skrzynkę (również spam).
            </p>
            <button
              onclick={close}
              class="mt-6 px-6 py-2 rounded-full border border-white/10 text-slate-400 text-sm hover:text-white hover:border-white/25 transition-all"
              >Zamknij</button
            >
          </div>
        {:else if status === "rate_limit"}
          <!-- Stan: zbyt wiele prób -->
          <div class="text-center py-6">
            <div
              class="w-14 h-14 rounded-full bg-amber-500/10 border border-amber-500/30 flex items-center justify-center mx-auto mb-4"
            >
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                <circle
                  cx="12"
                  cy="12"
                  r="9"
                  stroke="#f59e0b"
                  stroke-width="1.5"
                />
                <path
                  d="M12 7v5l3 3"
                  stroke="#f59e0b"
                  stroke-width="1.5"
                  stroke-linecap="round"
                />
              </svg>
            </div>
            <p class="text-white font-bold text-lg mb-2">Zbyt wiele prób</p>
            <p class="text-slate-400 text-sm">
              Spróbuj ponownie za <strong class="text-amber-400"
                >{rateLimitMinutes}
                {rateLimitMinutes === 1 ? "minutę" : "minut"}</strong
              >.
            </p>
            <button
              onclick={close}
              class="mt-6 px-6 py-2 rounded-full border border-white/10 text-slate-400 text-sm hover:text-white transition-all"
              >Zamknij</button
            >
          </div>
        {:else if status === "not_found"}
          <!-- Stan: brak zamówienia -->
          <div class="text-center py-6">
            <div
              class="w-14 h-14 rounded-full bg-red-500/10 border border-red-500/30 flex items-center justify-center mx-auto mb-4"
            >
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                <circle
                  cx="12"
                  cy="12"
                  r="9"
                  stroke="#ef4444"
                  stroke-width="1.5"
                />
                <path
                  d="M12 8v5M12 16v.5"
                  stroke="#ef4444"
                  stroke-width="1.5"
                  stroke-linecap="round"
                />
              </svg>
            </div>
            <p class="text-white font-bold text-lg mb-2">
              Nie znaleziono zamówienia
            </p>
            <p class="text-slate-400 text-sm mb-6">
              Nie znaleźliśmy zamówienia z podanym adresem email i numerem
              zamówienia. Sprawdź dane lub utwórz nowe zamówienie.
            </p>
            <div class="flex flex-col gap-3">
              <a
                href="/#pricing"
                onclick={close}
                class="block w-full py-3 rounded-2xl font-black text-sm uppercase tracking-widest text-white text-center transition-all"
                style="background: linear-gradient(135deg, #7c3aed, #a855f7); box-shadow: 0 0 20px rgba(168,85,247,0.3);"
              >
                ⚡ Kup dostęp do NEXUS
              </a>
              <button
                onclick={() => {
                  status = "idle";
                }}
                class="w-full py-2.5 rounded-2xl border border-white/10 text-slate-400 text-sm hover:text-white hover:border-white/25 transition-all"
              >
                Spróbuj ponownie
              </button>
            </div>
          </div>
        {:else}
          <!-- Formularz -->
          <p class="text-slate-400 text-sm mb-6 leading-relaxed">
            Podaj adres email użyty przy zakupie i numer zamówienia z emaila
            potwierdzającego. Wyślemy Ci link do edycji briefu lub ponownie do
            pierwszego wypełnienia.
          </p>

          <form onsubmit={handleSubmit} class="space-y-4">
            <div>
              <label
                class="block text-[11px] font-mono text-slate-300 uppercase tracking-widest mb-1.5 font-medium"
                for="brief-email"
              >
                Email zamówienia
              </label>
              <input
                id="brief-email"
                type="email"
                bind:value={email}
                required
                placeholder="twoj@email.pl"
                class="w-full bg-white/10 border border-white/20 rounded-xl px-4 py-3 text-white text-base placeholder-slate-400 focus:outline-none focus:border-cyan-500/50 focus:bg-white/15 transition-all font-mono"
              />
            </div>

            <div>
              <label
                class="block text-[11px] font-mono text-slate-300 uppercase tracking-widest mb-1.5 font-medium"
                for="brief-order"
              >
                Numer zamówienia
              </label>
              <input
                id="brief-order"
                type="text"
                bind:value={orderNumber}
                required
                placeholder="NX-2026-NNNNN"
                oninput={(e) => {
                  orderNumber = (
                    e.target as HTMLInputElement
                  ).value.toUpperCase();
                }}
                autocomplete="off"
                spellcheck={false}
                class="w-full bg-white/10 border border-white/20 rounded-xl px-4 py-3 text-white text-base placeholder-slate-400 focus:outline-none focus:border-cyan-500/50 focus:bg-white/15 transition-all font-mono uppercase"
              />
              <div class="text-[10px] text-slate-600 mt-1.5 font-mono">
                Format: NX-RRRR-NNNNN (np. NX-2026-12345)
              </div>
            </div>

            {#if status === "error"}
              <div
                class="text-red-400 text-xs font-mono bg-red-500/5 border border-red-500/15 rounded-lg px-3 py-2"
              >
                Wystąpił błąd. Spróbuj ponownie za chwilę.
              </div>
            {/if}

            <button
              type="submit"
              disabled={status === "loading"}
              class="w-full py-3.5 rounded-2xl font-black text-sm uppercase tracking-widest text-white transition-all disabled:opacity-50"
              style="background: linear-gradient(135deg, #7c3aed, #a855f7); box-shadow: 0 0 25px rgba(168,85,247,0.35);"
            >
              {#if status === "loading"}
                <span class="inline-flex items-center gap-2">
                  <svg
                    class="animate-spin w-4 h-4"
                    viewBox="0 0 24 24"
                    fill="none"
                  >
                    <circle
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      stroke-width="2"
                      class="opacity-25"
                    />
                    <path
                      d="M4 12a8 8 0 018-8"
                      stroke="currentColor"
                      stroke-width="2"
                      stroke-linecap="round"
                      class="opacity-75"
                    />
                  </svg>
                  Weryfikuję...
                </span>
              {:else}
                ⚡ Wyślij mi link
              {/if}
            </button>
          </form>
        {/if}
      </div>
    </div>
  </div>
{/if}
