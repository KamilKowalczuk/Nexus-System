<script lang="ts">
  let stage: 'auth-request' | 'otp-verify' | 'success' = $state('auth-request');
  let emailInput = $state('');
  let orderInput = $state('');
  let otpInput = $state('');
  
  let isLoading = $state(false);
  let errorMsg = $state('');

  async function sendOtp() {
    isLoading = true;
    errorMsg = '';
    try {
      const res = await fetch('/api/subscription/send-otp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: emailInput, orderNumber: orderInput }),
      });
      const data = await res.json();
      if (!res.ok) {
        errorMsg = data.error || 'Błąd logowania.';
        return;
      }
      stage = 'otp-verify';
    } catch (err) {
      errorMsg = 'Błąd krytyczny sieci. Spróbuj powonie później.';
    } finally {
      isLoading = false;
    }
  }

  async function verifyOtp() {
    isLoading = true;
    errorMsg = '';
    try {
      const res = await fetch('/api/subscription/verify-otp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: emailInput, orderNumber: orderInput, otp: otpInput }),
      });
      const data = await res.json();
      
      if (!res.ok) {
        errorMsg = data.error || 'Błąd weryfikacji kodu.';
        return;
      }
      
      stage = 'success';
      setTimeout(() => {
        window.location.href = '/manage-subscription/dashboard';
      }, 800);
      
    } catch (err) {
      errorMsg = 'Błąd krytyczny sieci.';
    } finally {
      isLoading = false;
    }
  }
</script>

<!-- ETAP 1: PODAJ EMAIL I NUMER ZAMÓWIENIA -->
{#if stage === 'auth-request'}
  <div class="max-w-lg w-full text-left z-10">
    <div class="rounded-3xl p-px bg-linear-to-b from-primary/50 to-primary/10">
      <div class="bg-black/90 rounded-3xl p-10 relative overflow-hidden">
        
        <!-- Progress -->
        <div class="flex items-center gap-3 mb-8">
          <div class="flex-1 h-1 rounded-full bg-primary/60"></div>
          <div class="flex-1 h-1 rounded-full bg-white/10"></div>
        </div>

        <div class="inline-block px-3 py-1 bg-primary/10 border border-primary/30 rounded-full text-[10px] font-mono text-primary uppercase tracking-widest mb-6">
          Logowanie do Panelu · Krok 1 z 2
        </div>

        <h2 class="font-display text-2xl font-bold uppercase tracking-tighter text-white mb-3">
          Zarządzaj NEXUS
        </h2>
        <p class="text-slate-400 text-sm mb-8 leading-relaxed">
          Uzyskaj bezpieczny dostęp do faktur i ustawień subskrypcji używając <strong>Emaila</strong> oraz <strong>Numeru Zamówienia</strong>.
        </p>

        <div class="space-y-4 relative z-10">
          <div>
            <label for="orderInput" class="block text-[10px] font-mono text-slate-500 uppercase tracking-widest mb-2">Numer Zamówienia</label>
            <input
              id="orderInput"
              type="text"
              bind:value={orderInput}
              class="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-white font-mono text-sm focus:outline-none focus:border-primary/50 transition-colors placeholder:text-slate-600 disabled:opacity-50"
              placeholder="np. NX-2026-12345"
              disabled={isLoading}
            />
          </div>

          <div>
            <label for="emailInput" class="block text-[10px] font-mono text-slate-500 uppercase tracking-widest mb-2">Adres email</label>
            <input
              id="emailInput"
              type="email"
              bind:value={emailInput}
              class="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-white font-mono text-sm focus:outline-none focus:border-primary/50 transition-colors placeholder:text-slate-600 disabled:opacity-50"
              placeholder="twoj@email.pl"
              disabled={isLoading}
            />
          </div>

          {#if errorMsg}
            <p class="text-red-400 text-xs font-mono bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-3">{errorMsg}</p>
          {/if}

          <button
            onclick={sendOtp}
            disabled={isLoading || !emailInput || !orderInput}
            class="w-full py-4 rounded-2xl font-display font-bold uppercase text-sm text-white transition-all duration-300 disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-2 mt-4"
            style="background: linear-gradient(135deg, hsl(270,60%,45%), hsl(280,70%,55%)); box-shadow: 0 0 30px hsl(270,60%,30%);"
          >
            {#if isLoading}
              <span class="material-symbols-outlined animate-spin text-sm">sync</span>
              Autoryzacja...
            {:else}
              <span class="material-symbols-outlined text-sm">security</span>
              Wyślij kod weryfikacyjny (OTP)
            {/if}
          </button>
        </div>

        <!-- Security badge -->
        <div class="mt-6 flex items-center gap-2 text-xs text-slate-600 font-mono">
          <span class="material-symbols-outlined text-sm text-slate-600">shield</span>
          Bezpieczny Kanał · Logowanie Passwordless
        </div>
      </div>
    </div>
  </div>

<!-- ETAP 2: KOD OTP -->
{:else if stage === 'otp-verify'}
  <div class="max-w-lg w-full text-left z-10">
    <div class="rounded-3xl p-px bg-linear-to-b from-primary/50 to-primary/10">
      <div class="bg-black/90 rounded-3xl p-10">
        
        <!-- Progress -->
        <div class="flex items-center gap-3 mb-8">
          <div class="flex-1 h-1 rounded-full bg-primary/60"></div>
          <div class="flex-1 h-1 rounded-full bg-primary/60"></div>
        </div>

        <div class="inline-block px-3 py-1 bg-primary/10 border border-primary/30 rounded-full text-[10px] font-mono text-primary uppercase tracking-widest mb-6">
          Logowanie do Panelu · Krok 2 z 2
        </div>

        <h2 class="font-display text-2xl font-bold uppercase tracking-tighter text-white mb-3">
          Wpisz kod z maila
        </h2>
        <p class="text-slate-400 text-sm mb-8">
          Wysłaliśmy 6-cyfrowy kod zabezpieczający na <strong class="text-white">{emailInput}</strong>.
        </p>

        <div class="space-y-4">
          <div>
            <label for="otpInput" class="block text-[10px] font-mono text-slate-500 uppercase tracking-widest mb-2">Kod OTP (6 cyfr)</label>
            <input
              id="otpInput"
              type="text"
              bind:value={otpInput}
              maxlength={6}
              class="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-4 text-white font-mono text-2xl text-center tracking-[0.5em] focus:outline-none focus:border-primary/50 transition-colors placeholder:text-slate-600 disabled:opacity-50"
              placeholder="000000"
              disabled={isLoading}
            />
          </div>

          {#if errorMsg}
            <p class="text-red-400 text-xs font-mono bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-3">{errorMsg}</p>
          {/if}

          <button
            onclick={verifyOtp}
            disabled={isLoading || otpInput.length !== 6}
            class="w-full py-4 rounded-2xl font-display font-bold uppercase text-sm text-white transition-all duration-300 disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-2 mt-2"
            style="background: linear-gradient(135deg, hsl(270,60%,45%), hsl(280,70%,55%)); box-shadow: 0 0 30px hsl(270,60%,30%);"
          >
            {#if isLoading}
              <span class="material-symbols-outlined animate-spin text-sm">sync</span>
              Weryfikacja...
            {:else}
              <span class="material-symbols-outlined text-sm">verified</span>
              Otwórz Panel
            {/if}
          </button>

          <button
            onclick={() => { stage = 'auth-request'; errorMsg = ''; otpInput = ''; }}
            class="w-full py-3 text-slate-500 font-mono text-xs uppercase tracking-widest hover:text-slate-300 transition-colors mt-2"
          >
            ← Zmień dane logowania
          </button>
        </div>
      </div>
    </div>
  </div>

<!-- ETAP 3: SUKCES -->
{:else if stage === 'success'}
  <div class="max-w-lg w-full text-center z-10">
    <div class="rounded-3xl p-px bg-linear-to-b from-green-500/50 to-green-900/10 mb-8">
      <div class="bg-black/90 rounded-3xl p-12 md:p-16">

        <span class="relative flex h-8 w-8 mx-auto mb-8">
          <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
          <span class="relative inline-flex rounded-full h-8 w-8 bg-green-50 shadow-[0_0_24px_#22c55e]"></span>
        </span>

        <h1 class="font-display text-2xl md:text-3xl font-bold uppercase tracking-tighter text-white mb-4">
          Autoryzacja udana
        </h1>
        <p class="text-slate-400 text-sm leading-relaxed mb-4">
          Otwieram bezpieczny tunel zarządzania...
        </p>

      </div>
    </div>
  </div>
{/if}
