<script lang="ts">
  let status = $state<'idle' | 'loading' | 'success' | 'error'>('idle');
  let errorMessage = $state('');

  let formData = $state({
    name: '',
    company: '',
    nip: '',
    phone: '',
    email: '',
    message: '',
    bot_field: '',
    privacyConsent: false,
  });

  let isNameTouched = $state(false);
  let isEmailTouched = $state(false);
  let isPhoneTouched = $state(false);
  let isMessageTouched = $state(false);

  function sanitizeName() {
    formData.name = formData.name.replace(/[^a-zA-ZąćęłńóśźżĄĆĘŁŃÓŚŹŻ\s\-]/g, '');
  }
  function sanitizeNip() {
    formData.nip = formData.nip.replace(/[^a-zA-Z0-9\-]/g, '').toUpperCase();
  }
  function sanitizePhone() {
    formData.phone = formData.phone.replace(/[^\d\s+()\-]/g, '');
  }

  let isEmailValid = $derived(
    !formData.email || /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/.test(formData.email)
  );
  let isPhoneValid = $derived(
    !formData.phone || formData.phone.replace(/\D/g, '').length >= 9
  );

  let validationErrors = $derived(
    [
      (!formData.name && isNameTouched) ? 'Imię i Nazwisko' : null,
      (!formData.email && isEmailTouched) ? 'Adres Email' : (!isEmailValid ? 'Nieprawidłowy Email' : null),
      (!formData.phone && isPhoneTouched) ? 'Telefon' : (!isPhoneValid ? 'Min. 9 cyfr telefonu' : null),
      (!formData.message && isMessageTouched) ? 'Treść Zapytania' : (isMessageTouched && formData.message.length < 10 ? 'Min. 10 znaków treści' : null),
      (!formData.privacyConsent) ? 'Polityka Prywatności' : null,
    ].filter(Boolean) as string[]
  );

  let canSubmit = $derived(
    formData.name !== '' &&
    formData.email !== '' &&
    isEmailValid &&
    formData.phone !== '' &&
    isPhoneValid &&
    formData.message.length >= 10 &&
    formData.privacyConsent
  );

  function sanitizeInput(str: string) {
    if (!str) return '';
    return str.replace(/[<>]/g, '').trim();
  }

    async function handleSubmit(e: Event) {
    e.preventDefault();
    status = 'loading';
    errorMessage = '';

    try {
      const sanitizedData = {
        name: sanitizeInput(formData.name),
        company: sanitizeInput(formData.company),
        nip: sanitizeInput(formData.nip),
        phone: sanitizeInput(formData.phone),
        email: sanitizeInput(formData.email),
        message: sanitizeInput(formData.message),
        privacyConsent: formData.privacyConsent,
        bot_field: formData.bot_field,
      };

      const response = await fetch('/api/contact', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(sanitizedData),
      });

      // Zabezpieczenie przed błędem JSON.parse gdy serwer zwróci HTML (np. 404 lub 500 z Netlify)
      const textResponse = await response.text();
      let data;
      try {
        data = textResponse ? JSON.parse(textResponse) : {};
      } catch (parseErr) {
        console.error("Błąd parsowania odpowiedzi:", textResponse);
        throw new Error('Serwer zwrócił nieprawidłową odpowiedź. Spróbuj ponownie.');
      }

      if (response.ok && data.success) {
        status = 'success';
        formData = {
          name: '', company: '', nip: '', phone: '',
          email: '', message: '', bot_field: '', privacyConsent: false,
        };
        isNameTouched = false;
        isEmailTouched = false;
        isPhoneTouched = false;
        isMessageTouched = false;
      } else {
        throw new Error(data.error || 'Serwer odrzucił zgłoszenie. Spróbuj ponownie za kilka minut.');
      }
    } catch (error: any) {
      status = 'error';
      errorMessage = error.message;
    }
  }
</script>

<div class="w-full">

  {#if status === 'success'}
    <!-- ─── SUCCESS ─── -->
    <div class="rounded-3xl p-[1px] bg-gradient-to-b from-green-500/50 to-green-900/10">
      <div class="w-full bg-black/90 rounded-3xl p-12 md:p-20 text-center">
        <span class="relative flex h-5 w-5 mx-auto mb-8">
          <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
          <span class="relative inline-flex rounded-full h-5 w-5 bg-green-500 shadow-[0_0_15px_#22c55e]"></span>
        </span>
        <h3 class="font-display text-3xl font-bold uppercase text-white mb-4">Wiadomość przyjęta</h3>
        <p class="text-slate-400 text-sm mb-10 max-w-md mx-auto">
          Twoje zapytanie trafiło do zespołu odpowiedzialnego za wdrożenia. Odpowiemy w ciągu 24 godzin roboczych
          z konkretną propozycją dalszych kroków – bez sprzedażowych „small talków”.
        </p>
        <button
          onclick={() => status = 'idle'}
          class="inline-flex items-center gap-3 border border-white/10 text-slate-400 font-mono uppercase text-[10px] tracking-widest px-8 py-4 rounded-full hover:border-primary/30 hover:text-primary transition-all duration-300"
        >
          Nowa wiadomość
        </button>
      </div>
    </div>

  {:else}
    <!-- ─── FORM ─── -->
    <form onsubmit={handleSubmit} autocomplete="off">
      <div class="hidden" aria-hidden="true">
        <input type="text" name="bot_field" tabindex={-1} bind:value={formData.bot_field} autocomplete="off" />
      </div>

      <div class="rounded-3xl p-[1px] bg-gradient-to-b from-white/10 to-white/[0.02] mb-6">
        <div class="bg-black/80 backdrop-blur-xl rounded-3xl p-8 md:p-12 space-y-8">

          <!-- Row 1: Name + Company -->
          <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div class="space-y-2">
              <label for="cf-name" class="text-[10px] font-mono text-slate-500 uppercase tracking-widest block">
                Imię i Nazwisko <span class="text-primary">*</span>
              </label>
              <input type="text" id="cf-name" required minlength={3} maxlength={100}
                bind:value={formData.name}
                oninput={sanitizeName}
                onblur={() => isNameTouched = true}
                disabled={status === 'loading'}
                class="w-full bg-white/[0.03] border border-white/10 rounded-xl px-5 py-4 text-sm text-white font-medium focus:outline-none focus:border-primary/50 focus:shadow-[0_0_15px_rgba(12,234,237,0.1)] transition-all duration-300 placeholder:text-slate-600 disabled:opacity-40"
                placeholder="Jan Kowalski"
              />
            </div>
            <div class="space-y-2">
              <label for="cf-company" class="text-[10px] font-mono text-slate-500 uppercase tracking-widest block">
                Firma
              </label>
              <input type="text" id="cf-company" maxlength={150}
                bind:value={formData.company}
                disabled={status === 'loading'}
                class="w-full bg-white/[0.03] border border-white/10 rounded-xl px-5 py-4 text-sm text-white font-medium focus:outline-none focus:border-primary/50 focus:shadow-[0_0_15px_rgba(12,234,237,0.1)] transition-all duration-300 placeholder:text-slate-600 disabled:opacity-40"
                placeholder="Opcjonalnie"
              />
            </div>
          </div>

          <!-- Row 2: Email + Phone -->
          <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div class="space-y-2">
              <label for="cf-email" class="text-[10px] font-mono uppercase tracking-widest flex justify-between {isEmailValid ? 'text-slate-500' : 'text-red-400'}">
                <span>Email <span class="text-primary">*</span></span>
                {#if !isEmailValid}<span class="text-red-400">Nieprawidłowy</span>{/if}
              </label>
              <input type="email" id="cf-email" required maxlength={100}
                bind:value={formData.email}
                onblur={() => isEmailTouched = true}
                disabled={status === 'loading'}
                class="w-full bg-white/[0.03] border rounded-xl px-5 py-4 text-sm font-medium focus:outline-none transition-all duration-300 placeholder:text-slate-600 disabled:opacity-40 {isEmailValid ? 'border-white/10 text-white focus:border-primary/50 focus:shadow-[0_0_15px_rgba(12,234,237,0.1)]' : 'border-red-500/30 text-red-400'}"
                placeholder="kontakt@firma.pl"
              />
            </div>
            <div class="space-y-2">
              <label for="cf-phone" class="text-[10px] font-mono uppercase tracking-widest flex justify-between {isPhoneValid ? 'text-slate-500' : 'text-red-400'}">
                <span>Telefon <span class="text-primary">*</span></span>
                {#if !isPhoneValid}<span class="text-red-400">Min 9 cyfr</span>{/if}
              </label>
              <input type="tel" id="cf-phone" required minlength={9} maxlength={20}
                bind:value={formData.phone}
                oninput={sanitizePhone}
                onblur={() => isPhoneTouched = true}
                disabled={status === 'loading'}
                class="w-full bg-white/[0.03] border rounded-xl px-5 py-4 text-sm font-medium focus:outline-none transition-all duration-300 placeholder:text-slate-600 disabled:opacity-40 {isPhoneValid ? 'border-white/10 text-white focus:border-primary/50 focus:shadow-[0_0_15px_rgba(12,234,237,0.1)]' : 'border-red-500/30 text-red-400'}"
                placeholder="+48 000 000 000"
              />
            </div>
          </div>

          <!-- Row 3: NIP -->
          <div class="space-y-2">
            <label for="cf-nip" class="text-[10px] font-mono text-slate-500 uppercase tracking-widest block">
              NIP
            </label>
            <input type="text" id="cf-nip" maxlength={20}
              bind:value={formData.nip}
              oninput={sanitizeNip}
              disabled={status === 'loading'}
              class="w-full bg-white/[0.03] border border-white/10 rounded-xl px-5 py-4 text-sm text-white font-medium focus:outline-none focus:border-primary/50 focus:shadow-[0_0_15px_rgba(12,234,237,0.1)] transition-all duration-300 placeholder:text-slate-600 disabled:opacity-40"
              placeholder="Opcjonalnie"
            />
          </div>

          <!-- Row 4: Message -->
          <div class="space-y-2">
            <label for="cf-message" class="text-[10px] font-mono text-slate-500 uppercase tracking-widest block">
              Treść Zapytania <span class="text-primary">*</span>
            </label>
            <textarea id="cf-message" required minlength={10} maxlength={2000}
              bind:value={formData.message}
              onblur={() => isMessageTouched = true}
              disabled={status === 'loading'}
              rows={4}
              class="w-full bg-white/[0.03] border border-white/10 rounded-xl px-5 py-4 text-sm text-white font-medium focus:outline-none focus:border-primary/50 focus:shadow-[0_0_15px_rgba(12,234,237,0.1)] transition-all duration-300 placeholder:text-slate-600 disabled:opacity-40 resize-none"
              placeholder="Opisz czego potrzebujesz..."
            ></textarea>
          </div>

        </div>
      </div>

      <!-- Error -->
      {#if status === 'error'}
        <div class="mb-6 rounded-xl border border-red-500/20 bg-red-500/5 px-6 py-4">
          <span class="font-mono text-[10px] text-red-400 uppercase tracking-widest">SYS_ERR: {errorMessage}</span>
        </div>
      {/if}

      <!-- Footer: Consent + Submit -->
      <div class="flex flex-col md:flex-row items-start md:items-center justify-between gap-8">
        <!-- Privacy checkbox -->
        <div class="flex items-start gap-3 max-w-md">
          <button
            type="button"
            role="checkbox"
            aria-checked={formData.privacyConsent}
            aria-label="Akceptuję Politykę Prywatności"
            onclick={() => formData.privacyConsent = !formData.privacyConsent}
            disabled={status === 'loading'}
            class="relative mt-0.5 shrink-0 cursor-pointer focus:outline-none"
          >
            <div class="size-5 rounded border-2 flex items-center justify-center transition-all duration-300 {formData.privacyConsent ? 'bg-primary border-primary shadow-[0_0_10px_rgba(12,234,237,0.3)]' : 'bg-transparent border-slate-600 hover:border-slate-500'}">
              {#if formData.privacyConsent}
                <svg class="w-3 h-3 text-bg-dark" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7"></path>
                </svg>
              {/if}
            </div>
          </button>
          <button
            type="button"
            onclick={() => formData.privacyConsent = !formData.privacyConsent}
            class="text-[11px] text-slate-500 leading-relaxed text-left cursor-pointer hover:text-slate-400 transition-colors"
          >
            Akceptuję <a href="/polityka-prywatnosci" target="_blank" rel="noopener noreferrer" class="text-white hover:text-primary transition-colors font-semibold" onclick={(e: MouseEvent) => e.stopPropagation()}>Politykę Prywatności</a> i zgadzam się na kontakt wyłącznie w sprawie konfiguracji i działania NEXUS.
          </button>
        </div>

        <!-- Validation + Submit -->
        <div class="flex flex-col items-start md:items-end gap-4 shrink-0 w-full md:w-auto">
          {#if !canSubmit && (isNameTouched || isEmailTouched || isPhoneTouched || isMessageTouched)}
            <div class="flex flex-wrap gap-2">
              {#each validationErrors as error}
                <span class="text-[9px] font-mono text-yellow-500/80 uppercase tracking-widest bg-yellow-500/5 border border-yellow-500/10 px-2 py-1 rounded-full">
                  {error}
                </span>
              {/each}
            </div>
          {:else if canSubmit}
            <div class="flex items-center gap-2">
              <span class="size-1.5 bg-green-500 rounded-full shadow-[0_0_6px_#22c55e]"></span>
              <span class="text-[10px] font-mono text-green-400/80 uppercase tracking-widest">Gotowe</span>
            </div>
          {/if}

          <button
            type="submit"
            disabled={status === 'loading' || !canSubmit}
            class="inline-flex w-full md:w-auto items-center justify-center gap-3 bg-primary text-bg-dark font-display font-bold uppercase text-xs px-12 py-5 rounded-full hover:brightness-110 hover:scale-105 transition-all duration-300 neon-shadow-cyan disabled:opacity-20 disabled:cursor-not-allowed disabled:hover:scale-100 disabled:hover:brightness-100"
          >
            {#if status === 'loading'}
              <div class="size-4 animate-spin rounded-full border-2 border-bg-dark border-t-transparent"></div>
              <span>Transmisja...</span>
            {:else}
              <span>Wyślij Zapytanie</span>
              <span class="material-symbols-outlined text-sm">send</span>
            {/if}
          </button>
        </div>
      </div>
    </form>
  {/if}
</div>
