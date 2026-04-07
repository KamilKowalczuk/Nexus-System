<script lang="ts">
  let isFromStripe = $state(false);
  let isLoading = $state(true);

  $effect(() => {
    const params = new URLSearchParams(window.location.search);
    isFromStripe = params.get('from') === 'stripe';
    isLoading = false;
  });

  const diagnostics = [
    'Sprawdź poprawność danych karty płatniczej.',
    'Upewnij się, że masz wystarczające środki oraz odblokowane płatności online.',
    'Jeśli płacisz z konta firmowego, sprawdź wewnętrzne limity bezpieczeństwa.',
    'Jeżeli problem wraca – daj nam znać, zanim odłożysz decyzję o wdrożeniu o kolejny miesiąc.',
  ];
</script>

{#if isLoading}
  <div class="max-w-2xl w-full relative z-10">
    <div class="rounded-3xl p-px bg-linear-to-b from-red-500/50 to-red-900/10">
      <div class="bg-slate-950/60 backdrop-blur-3xl rounded-3xl p-12 md:p-16 flex flex-col items-center">
        <span class="material-symbols-outlined text-4xl text-red-400 animate-spin mb-6">sync</span>
        <p class="font-mono text-sm text-slate-400 uppercase tracking-widest">Ładowanie...</p>
      </div>
    </div>
  </div>

{:else if !isFromStripe}
  <!-- Bezpośrednie wejście bez Stripe – zablokowane -->
  <div class="max-w-2xl w-full relative z-10">
    <div class="rounded-3xl p-px bg-linear-to-b from-red-500/30 to-red-900/5">
      <div class="bg-slate-950/60 backdrop-blur-3xl rounded-3xl p-12 md:p-16 text-center">

        <div class="inline-flex items-center justify-center gap-3 px-4 py-1.5 bg-red-500/10 border border-red-500/20 rounded-full text-[10px] font-mono text-red-400/70 uppercase tracking-widest mb-6">
          <span class="material-symbols-outlined text-3xl text-red-400/80">lock</span>
          <span>Dostęp ograniczony</span>
        </div>

        <h1 class="font-display text-3xl md:text-4xl font-bold uppercase tracking-tighter text-white mb-4">
          Ta strona jest niedostępna
        </h1>
        <p class="text-slate-500 text-sm leading-relaxed mb-8 max-w-md mx-auto">
          Strona błędu płatności jest dostępna wyłącznie po próbie zakupu przez system Stripe.
        </p>

        <a
          href="/"
          class="inline-flex items-center gap-3 border border-white/10 text-slate-400 font-mono uppercase text-[10px] tracking-widest px-8 py-4 rounded-full hover:border-primary/30 hover:text-primary transition-all duration-300"
        >
          <span class="material-symbols-outlined text-sm">arrow_back</span>
          Wróć na stronę główną
        </a>
      </div>
    </div>
  </div>

{:else}
  <!-- Przyszedł ze Stripe po nieudanej płatności -->
  <div class="max-w-2xl w-full relative z-10">
    <div class="rounded-3xl p-px bg-linear-to-b from-red-500/50 to-red-900/10 mb-12">
      <div class="bg-slate-950/60 backdrop-blur-3xl rounded-3xl p-12 md:p-16">

        <!-- Pulsing dot (red) -->
        <span class="relative flex h-6 w-6 mx-auto mb-10">
          <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
          <span class="relative inline-flex rounded-full h-6 w-6 bg-red-500 shadow-[0_0_20px_#ef4444]"></span>
        </span>

        <div class="inline-block px-4 py-1.5 bg-red-500/10 border border-red-500/30 rounded-full text-[10px] font-mono text-red-400 uppercase tracking-widest mb-6">
          Płatność odrzucona
        </div>

        <h1 class="font-display text-4xl md:text-5xl font-bold uppercase tracking-tighter text-white mb-6">
          Transakcja<br />
          <span class="text-red-400">nie została zrealizowana</span>
        </h1>

        <p class="text-slate-400 text-sm leading-relaxed mb-10 max-w-md mx-auto">
          Żadna kwota nie została pobrana. Najczęstsze powody to błędne dane karty, limity banku lub blokada płatności
          online. Jeśli powtórzysz próbę później, a błąd się utrzyma – skontaktuj się z nami, zanim zrezygnujesz.
        </p>

        <!-- Error diagnostics -->
        <div class="glass rounded-2xl p-6 border border-red-500/10 text-left mb-10">
          <div class="flex justify-between items-center text-xs font-mono uppercase text-slate-500 mb-5 tracking-widest">
            <span>Diagnostyka</span>
            <span class="text-red-400 flex items-center gap-1.5">
              <span class="inline-block w-1.5 h-1.5 rounded-full bg-red-400 animate-pulse"></span>
              Nieudana transakcja
            </span>
          </div>
          <div class="space-y-3">
            {#each diagnostics as item}
              <div class="flex items-start gap-3 text-slate-400 text-sm">
                <span class="material-symbols-outlined text-red-500/50 text-base shrink-0 mt-0.5">error_outline</span>
                {item}
              </div>
            {/each}
          </div>
        </div>

        <!-- Actions -->
        <div class="flex flex-col sm:flex-row gap-4 justify-center">
          <a
            href="/#pricing"
            class="inline-flex items-center justify-center gap-3 bg-red-500/10 hover:bg-red-500/20 border border-red-500/30 hover:border-red-500/50 text-red-400 font-display font-bold uppercase text-sm tracking-widest px-8 py-4 rounded-2xl transition-all duration-300"
          >
            <span class="material-symbols-outlined text-base">refresh</span>
            Spróbuj ponownie
          </a>
          <a
            href="/#contact"
            class="inline-flex items-center justify-center gap-3 border border-white/10 text-slate-400 font-mono uppercase text-[10px] tracking-widest px-8 py-4 rounded-full hover:border-white/20 hover:text-white transition-all duration-300"
          >
            <span class="material-symbols-outlined text-sm">support_agent</span>
            Skontaktuj się z nami
          </a>
        </div>

      </div>
    </div>

    <!-- Status bar -->
    <div class="font-mono text-[9px] text-slate-600 uppercase tracking-widest text-center">
      STATUS PŁATNOŚCI: NIEUDANA | NEXUS AGENT v2.4 | KARTA NIEZOBOWIĄZANA, MOŻESZ SPRÓBOWAĆ PONOWNIE ✗
    </div>
  </div>
{/if}
