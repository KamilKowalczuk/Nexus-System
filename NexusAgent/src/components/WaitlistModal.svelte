<script lang="ts">
  interface Props {
    emailsPerDay?: number;
    onClose: () => void;
    onSuccess?: () => void;
  }

  let { emailsPerDay = 20, onClose, onSuccess }: Props = $props();

  let firstName = $state("");
  let lastName = $state("");
  let email = $state("");
  let phone = $state("");
  let bot_field = $state("");

  let isLoading = $state(false);
  let isSuccess = $state(false);
  let errorMessage = $state("");

  let isEmailTouched = $state(false);
  let isPhoneTouched = $state(false);
  let acceptedPrivacy = $state(false);

  // Sanitization functions
  function sanitizeName(type: "first" | "last") {
    if (type === "first") {
      firstName = firstName.replace(/[^a-zA-ZąćęłńóśźżĄĆĘŁŃÓŚŹŻ\s\-]/g, "");
    } else {
      lastName = lastName.replace(/[^a-zA-ZąćęłńóśźżĄĆĘŁŃÓŚŹŻ\s\-]/g, "");
    }
  }

  function sanitizePhone() {
    phone = phone.replace(/[^\d\s+\-()]/g, "");
  }

  function sanitizeHTML(str: string) {
    if (!str) return "";
    return str.replace(/[<>]/g, "").trim();
  }

  // Validation
  let isEmailValid = $derived(
    !email || /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/.test(email),
  );

  let isPhoneValid = $derived(!phone || phone.replace(/\D/g, "").length >= 9);

  let canSubmit = $derived(
    firstName.trim().length > 0 &&
      lastName.trim().length > 0 &&
      email.trim().length > 0 &&
      isEmailValid &&
      (phone === "" || isPhoneValid) &&
      acceptedPrivacy,
  );

  async function handleSubmit(e: Event) {
    e.preventDefault();
    if (isLoading || !canSubmit) return;

    // Honeypot check - silently succeed for bots
    if (bot_field) {
      isSuccess = true;
      setTimeout(() => onClose(), 3000);
      return;
    }

    errorMessage = "";
    isLoading = true;

    try {
      const res = await fetch("/api/waitlist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          firstName: sanitizeHTML(firstName),
          lastName: sanitizeHTML(lastName),
          email: sanitizeHTML(email).toLowerCase(),
          phone: sanitizeHTML(phone),
          emailsPerDay,
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        errorMessage = data.error || "Wystąpił błąd. Spróbuj ponownie.";
        return;
      }

      isSuccess = true;
      onSuccess?.();

      // Auto-close after 3s
      setTimeout(() => {
        onClose();
      }, 3000);
    } catch (err: any) {
      errorMessage = "Błąd połączenia. Sprawdź internet i spróbuj ponownie.";
    } finally {
      isLoading = false;
    }
  }
</script>

<!-- Outer gradient border wrapper matching ContactForm -->
<div
  class="rounded-3xl p-px-gradient-to-b from-white/10 to-white/2 w-full max-w-lg mx-auto shadow-2xl"
  onclick={(e) => e.stopPropagation()}
  role="none"
>
  <!-- Inner glass box -->
  <div
    class="bg-black/95 backdrop-blur-xl rounded-3xl p-6 md:p-8 relative overflow-hidden"
  >
    <!-- Close Button -->
    <button
      onclick={onClose}
      class="absolute top-6 right-6 size-8 flex items-center justify-center text-slate-500 hover:text-white transition-colors z-50 bg-black/50 rounded-full md:bg-transparent"
      aria-label="Zamknij"
    >
      <span class="material-symbols-outlined text-xl">close</span>
    </button>

    {#if !isSuccess}
      <!-- Header -->
      <div class="mb-8 relative z-10">
        <div class="inline-flex items-center gap-2 mb-4">
          <span
            class="size-1.5 bg-primary rounded-full shadow-[0_0_6px_#0ceaed] animate-pulse"
          ></span>
          <span
            class="text-[10px] font-mono text-primary uppercase tracking-widest"
            >Lista Oczekujących</span
          >
        </div>
        <h3
          class="font-display text-2xl md:text-3xl font-bold uppercase tracking-tight text-white mb-2"
        >
          Zarezerwuj miejsce
        </h3>
        <p class="text-slate-400 text-sm leading-relaxed">
          Przykro nam, brak wolnych miejsc. Zostaw kontakt, a powiadomimy Cię
          jako pierwszego, gdy będziemy mogli wdrożyć NEXUS w Twojej firmie.
        </p>
      </div>

      <!-- Form -->
      <form
        onsubmit={handleSubmit}
        class="space-y-6 relative z-10"
        autocomplete="off"
      >
        <!-- Honeypot -->
        <div class="hidden" aria-hidden="true">
          <input
            type="text"
            name="bot_field"
            tabindex="-1"
            bind:value={bot_field}
            autocomplete="off"
          />
        </div>

        <div class="flex flex-col md:flex-row gap-6 w-full">
          <div class="space-y-2 flex-1 min-w-0">
            <label
              for="wl-firstname"
              class="text-[11px] font-mono text-slate-300 uppercase tracking-widest block font-medium"
            >
              Imię <span class="text-primary">*</span>
            </label>
            <input
              id="wl-firstname"
              bind:value={firstName}
              oninput={() => sanitizeName("first")}
              type="text"
              required
              disabled={isLoading}
              placeholder="Jan"
              class="w-full bg-white/10 border border-white/20 rounded-xl px-5 py-4 text-base text-white font-medium focus:outline-none focus:border-primary/50 focus:bg-white/15 focus:shadow-[0_0_15px_rgba(12,234,237,0.15)] transition-all duration-300 placeholder:text-slate-400 disabled:opacity-40"
            />
          </div>
          <div class="space-y-2 flex-1 min-w-0">
            <label
              for="wl-lastname"
              class="text-[11px] font-mono text-slate-300 uppercase tracking-widest block font-medium"
            >
              Nazwisko <span class="text-primary">*</span>
            </label>
            <input
              id="wl-lastname"
              bind:value={lastName}
              oninput={() => sanitizeName("last")}
              type="text"
              required
              disabled={isLoading}
              placeholder="Kowalski"
              class="w-full bg-white/10 border border-white/20 rounded-xl px-5 py-4 text-base text-white font-medium focus:outline-none focus:border-primary/50 focus:bg-white/15 focus:shadow-[0_0_15px_rgba(12,234,237,0.15)] transition-all duration-300 placeholder:text-slate-400 disabled:opacity-40"
            />
          </div>
        </div>

        <div class="space-y-2">
          <label
            for="wl-email"
            class="text-[11px] font-mono uppercase tracking-widest flex justify-between {isEmailValid
              ? 'text-slate-300 font-medium'
              : 'text-red-400'}"
          >
            <span>Email służbowy <span class="text-primary">*</span></span>
            {#if !isEmailValid && isEmailTouched}<span class="text-red-400"
                >Nieprawidłowy</span
              >{/if}
          </label>
          <input
            id="wl-email"
            bind:value={email}
            onblur={() => (isEmailTouched = true)}
            type="email"
            required
            disabled={isLoading}
            placeholder="jan@firma.pl"
            class="w-full bg-white/10 border rounded-xl px-5 py-4 text-base font-medium focus:outline-none transition-all duration-300 placeholder:text-slate-400 disabled:opacity-40 {isEmailValid ||
            !isEmailTouched
              ? 'border-white/20 text-white focus:border-primary/50 focus:bg-white/15 focus:shadow-[0_0_15px_rgba(12,234,237,0.15)]'
              : 'border-red-500/50 text-red-400 bg-red-500/10'}"
          />
        </div>

        <div class="space-y-2">
          <label
            for="wl-phone"
            class="text-[11px] font-mono uppercase tracking-widest flex justify-between {isPhoneValid
              ? 'text-slate-300 font-medium'
              : 'text-red-400'}"
          >
            <span
              >Telefon <span class="text-slate-600 lowercase"
                >(opcjonalnie)</span
              ></span
            >
            {#if !isPhoneValid && isPhoneTouched}<span class="text-red-400"
                >Min. 9 cyfr</span
              >{/if}
          </label>
          <input
            id="wl-phone"
            bind:value={phone}
            oninput={sanitizePhone}
            onblur={() => (isPhoneTouched = true)}
            type="tel"
            disabled={isLoading}
            placeholder="+48 000 000 000"
            class="w-full bg-white/10 border rounded-xl px-5 py-4 text-base font-medium focus:outline-none transition-all duration-300 placeholder:text-slate-400 disabled:opacity-40 {isPhoneValid ||
            !isPhoneTouched
              ? 'border-white/20 text-white focus:border-primary/50 focus:bg-white/15 focus:shadow-[0_0_15px_rgba(12,234,237,0.15)]'
              : 'border-red-500/50 text-red-400 bg-red-500/10'}"
          />
        </div>

        {#if errorMessage}
          <div
            class="rounded-xl border border-red-500/20 bg-red-500/5 px-5 py-3"
          >
            <span
              class="font-mono text-[10px] text-red-400 uppercase tracking-widest"
              >SYS_ERR: {errorMessage}</span
            >
          </div>
        {/if}

        <div class="flex items-start gap-4 mt-2 mb-4">
          <div class="relative flex items-start pt-0.5 shrink-0">
            <input 
              id="wl-privacy" 
              type="checkbox" 
              bind:checked={acceptedPrivacy}
              class="peer size-5 appearance-none rounded-md border border-white/20 bg-white/5 checked:bg-primary checked:border-primary focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all cursor-pointer"
            />
            <svg class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-3 h-3 pointer-events-none opacity-0 peer-checked:opacity-100 text-bg-dark transition-opacity" viewBox="0 0 14 10" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M1 5L4.5 8.5L13 1" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </div>
          <label for="wl-privacy" class="text-[11px] text-slate-300 font-mono leading-relaxed cursor-pointer select-none">
            Zapoznałem się z <a
              href="/polityka-prywatnosci"
              target="_blank"
              class="text-white hover:text-primary underline decoration-white/30 hover:decoration-primary/50 transition-colors"
              >polityką prywatności</a
            > i akceptuję jej warunki, w szczególności dotyczące zgody na kontakt. <span class="text-primary font-bold">*</span>
          </label>
        </div>

        <div class="pt-2">
          <button
            type="submit"
            disabled={isLoading || !canSubmit}
            class="w-full inline-flex items-center justify-center gap-3 bg-primary text-bg-dark font-display font-bold uppercase text-xs px-12 py-5 rounded-full hover:brightness-110 hover:scale-[1.02] transition-all duration-300 neon-shadow-cyan disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:scale-100 disabled:hover:brightness-100"
          >
            {#if isLoading}
              <div
                class="size-4 animate-spin rounded-full border-2 border-bg-dark border-t-transparent"
              ></div>
              <span>Przetwarzanie...</span>
            {:else}
              <span>Zapisz na listę</span>
              <span class="material-symbols-outlined text-sm"
                >arrow_forward</span
              >
            {/if}
          </button>
        </div>

        <p class="text-center text-[10px] text-slate-600 font-mono mt-4">
          Dane szyfrowane. Zero spamu.
        </p>
      </form>
    {:else}
      <!-- Success state -->
      <div class="text-center py-12 relative z-10">
        <span class="relative flex h-12 w-12 mx-auto mb-8">
          <span
            class="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-40"
          ></span>
          <span
            class="relative inline-flex rounded-full h-12 w-12 bg-primary shadow-[0_0_20px_rgba(12,234,237,0.5)] items-center justify-center"
          >
            <span class="material-symbols-outlined text-bg-dark text-xl"
              >done</span
            >
          </span>
        </span>
        <h3
          class="font-display text-2xl font-bold uppercase tracking-tight text-white mb-3"
        >
          Miejsce zarezerwowane
        </h3>
        <p class="text-slate-400 text-sm leading-relaxed max-w-xs mx-auto mb-8">
          Otrzymasz powiadomienie na adres <strong
            class="text-white font-medium">{email}</strong
          > natychmiast, gdy zwolni się slot w systemie.
        </p>
        <div
          class="text-[10px] font-mono text-slate-600 uppercase tracking-widest"
        >
          Zamykanie okna...
        </div>
      </div>
    {/if}
  </div>
</div>
