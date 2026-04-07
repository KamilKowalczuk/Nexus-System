<script lang="ts">
  import { onMount } from 'svelte';

  type DashboardData = {
    orderNumber: string;
    email: string;
    status: 'active' | 'canceled' | 'past_due';
    dailyLimit: number;
    monthlyAmount: number;
    currentPeriodEnd?: string;
    cancelAtDate?: string;
    upcomingInvoice?: { amount_due: number; next_payment_attempt: string; };
    payments: any[];
  };

  let data = $state<DashboardData | null>(null);
  let isLoading = $state(true);
  let errorMsg = $state('');
  let isCanceling = $state(false);

  let showCancelConfirmModal = $state(false);
  let showCancelSuccessModal = $state(false);
  let cancelErrorMsg = $state('');

  onMount(async () => {
    try {
      const res = await fetch('/api/subscription/dashboard-data');
      if (!res.ok) {
        if (res.status === 401) {
          window.location.href = '/manage-subscription';
          return;
        }
        errorMsg = 'Błąd pobierania danych.';
        return;
      }
      data = await res.json();
    } catch {
      errorMsg = 'Krytyczny błąd połączenia z serwerem.';
    } finally {
      isLoading = false;
    }
  });

  function requestCancel() {
    showCancelConfirmModal = true;
  }

  async function confirmCancel() {
    showCancelConfirmModal = false;
    isCanceling = true;
    cancelErrorMsg = '';
    
    try {
      const res = await fetch('/api/subscription/cancel', { method: 'POST' });
      const result = await res.json();

      if (!res.ok) {
        cancelErrorMsg = result.error || 'Wystąpił błąd podczas anulowania.';
        return;
      }
      
      showCancelSuccessModal = true;
    } catch {
      cancelErrorMsg = 'Krytyczny błąd sieci podczas próby anulowania.';
    } finally {
      isCanceling = false;
    }
  }

  function closeSuccessModal() {
    showCancelSuccessModal = false;
    window.location.reload();
  }

  function formatDate(iso: string) {
    if (!iso) return '-';
    return new Date(iso).toLocaleDateString('pl-PL', {
      year: 'numeric', month: 'long', day: 'numeric'
    });
  }

  async function logout() {
    await fetch('/api/subscription/logout', { method: 'POST' });
    window.location.href = "/manage-subscription";
  }
</script>

{#if isLoading}
  <div class="flex flex-col items-center justify-center min-h-[500px]">
    <div class="relative w-24 h-24 mb-8">
      <div class="absolute inset-0 rounded-full border border-primary/20 bg-primary/5 animate-ping"></div>
      <div class="absolute inset-2 rounded-full border border-primary/40 bg-primary/10 animate-pulse"></div>
      <div class="absolute inset-8 rounded-full bg-primary shadow-[0_0_30px_#a855f7]"></div>
    </div>
    <div class="inline-block px-4 py-1.5 bg-primary/10 border border-primary/30 rounded-full text-[10px] font-mono text-primary uppercase tracking-widest">
      Skanowanie Bazy Danych...
    </div>
  </div>
{:else if errorMsg}
  <div class="max-w-xl mx-auto text-center mt-20">
    <div class="rounded-3xl p-px bg-linear-to-b from-red-500/40 to-transparent">
      <div class="bg-black/90 rounded-3xl p-12 backdrop-blur-xl">
        <span class="material-symbols-outlined text-5xl text-red-500 mb-6 block">gpp_bad</span>
        <h2 class="text-3xl font-bold font-display uppercase tracking-tight text-white mb-4">Odmowa Dostępu</h2>
        <p class="text-slate-400 text-sm mb-8">{errorMsg}</p>
        <button onclick={logout} class="border border-white/10 text-slate-400 font-mono text-[10px] uppercase tracking-widest px-8 py-4 rounded-full hover:border-primary/30 hover:text-primary transition-all">
          Powrót do logowania
        </button>
      </div>
    </div>
  </div>
{:else if data}
  <!-- HEADER -->
  <div class="flex flex-col md:flex-row md:items-end justify-between gap-6 mb-12 relative z-10">
    <div>
      <div class="inline-flex items-center gap-2 px-3 py-1 bg-white/5 border border-white/10 rounded-full mb-6">
        <span class="w-1.5 h-1.5 rounded-full {data.status === 'active' ? 'bg-green-500 animate-pulse' : (data.status === 'canceled' ? 'bg-orange-500' : 'bg-red-500')}"></span>
        <span class="text-[9px] font-mono text-slate-300 uppercase tracking-widest">
          Status: {data.status === 'active' ? 'W PEŁNI AKTYWNY' : (data.status === 'canceled' ? 'ZLECENIE WYGASZENIA' : 'ZALEGŁOŚĆ')}
        </span>
      </div>
      <h1 class="text-4xl md:text-5xl font-display font-bold text-white uppercase tracking-tighter mb-4 shadow-sm">Twój Agent</h1>
      <div class="flex flex-wrap items-center gap-4 text-xs font-mono text-slate-500 uppercase tracking-widest">
        <div class="flex items-center gap-2">
          <span class="material-symbols-outlined text-sm text-slate-600">badge</span>
          <span class="text-primary">{data.orderNumber}</span>
        </div>
        <div class="w-1 h-1 rounded-full bg-slate-700 hidden sm:block"></div>
        <div class="flex items-center gap-2">
          <span class="material-symbols-outlined text-sm text-slate-600">mail</span>
          <span class="text-slate-300">{data.email}</span>
        </div>
      </div>
    </div>
    
    <button onclick={logout} class="shrink-0 inline-flex items-center gap-2 border border-white/10 text-slate-400 font-mono text-[10px] uppercase tracking-widest px-6 py-3 rounded-full hover:border-primary/30 hover:text-primary transition-all">
      <span class="material-symbols-outlined text-[14px]">logout</span> Wyloguj
    </button>
  </div>

  {#if cancelErrorMsg}
    <div class="mb-8 p-1 rounded-2xl bg-linear-to-r from-red-500/20 to-transparent">
      <div class="bg-black p-4 rounded-xl border border-red-500/30 text-red-500 text-sm font-mono flex items-center gap-3">
        <span class="material-symbols-outlined shrink-0 text-xl">error</span>
        {cancelErrorMsg}
      </div>
    </div>
  {/if}

  <div class="grid grid-cols-1 lg:grid-cols-12 gap-6 relative z-10">
    <!-- LEWA KOLUMNA (PARAMETRY & AKCJE) -->
    <div class="lg:col-span-8 space-y-6">
      
      <!-- PARAMETRY SILNIKA -->
      <div class="rounded-3xl p-px bg-linear-to-b from-white/10 to-transparent">
        <div class="bg-black/90 p-8 rounded-3xl backdrop-blur-xl relative overflow-hidden">
          
          <div class="absolute top-0 right-0 p-6 opacity-5 pointer-events-none">
            <span class="material-symbols-outlined" style="font-size: 140px;">manufacturing</span>
          </div>

          <h2 class="text-[10px] font-mono uppercase tracking-widest text-slate-500 mb-6 flex items-center gap-2">
            <span class="material-symbols-outlined text-sm">memory</span>
            Parametry Silnika
          </h2>
          
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div class="bg-white/5 border border-white/5 hover:border-white/10 rounded-2xl p-6 transition-colors">
              <div class="flex items-center gap-3 mb-4">
                 <div class="w-8 h-8 rounded-full bg-primary/10 border border-primary/20 flex items-center justify-center">
                   <span class="material-symbols-outlined text-primary text-sm">all_inclusive</span>
                 </div>
                 <span class="text-[10px] font-mono text-slate-400 uppercase tracking-widest">Przepustowość</span>
              </div>
              <div class="text-3xl font-display font-bold text-white tracking-tighter">{data.dailyLimit}</div>
              <div class="text-[10px] font-mono text-slate-500 uppercase tracking-widest mt-1">maili / dobę</div>
            </div>
            
            <div class="bg-white/5 border border-white/5 hover:border-white/10 rounded-2xl p-6 transition-colors">
              <div class="flex items-center gap-3 mb-4">
                 <div class="w-8 h-8 rounded-full bg-blue-500/10 border border-blue-500/20 flex items-center justify-center">
                   <span class="material-symbols-outlined text-blue-400 text-sm">payments</span>
                 </div>
                 <span class="text-[10px] font-mono text-slate-400 uppercase tracking-widest">Koszt Operacyjny</span>
              </div>
              <div class="text-3xl font-display font-bold text-white tracking-tighter">{data.monthlyAmount}</div>
              <div class="text-[10px] font-mono text-slate-500 uppercase tracking-widest mt-1">PLN / m-c</div>
            </div>
          </div>
        </div>
      </div>

      <!-- STATUS & AKCJE -->
      <div class="rounded-3xl p-px {data.status === 'active' ? 'bg-linear-to-b from-primary/30 to-transparent' : 'bg-linear-to-b from-orange-500/30 to-transparent'}">
        <div class="bg-black/90 p-8 rounded-3xl backdrop-blur-xl relative overflow-hidden flex flex-col md:flex-row md:items-center justify-between gap-8">
          
          <div class="relative z-10 flex-1">
            {#if data.status === 'active'}
              <h2 class="text-2xl font-display font-bold text-white tracking-tighter uppercase mb-2">Cykl Operacyjny Włączony</h2>
              <p class="text-sm text-slate-400 leading-relaxed mb-4 lg:mb-0">
                Infrastruktura działa płynnie. Następne automatyczne odnowienie i fakturowanie nastąpi w dniu: 
                <strong class="text-white bg-white/10 px-2 py-0.5 rounded ml-1 font-mono text-xs">{data.upcomingInvoice ? formatDate(data.upcomingInvoice.next_payment_attempt) : formatDate(data.currentPeriodEnd || '')}</strong>.
              </p>
            {:else if data.status === 'canceled'}
              <h2 class="text-2xl font-display font-bold text-orange-400 tracking-tighter uppercase mb-2">Protokół Samokasowania Aktywowany</h2>
              <p class="text-sm text-slate-400 leading-relaxed mb-4 lg:mb-0">
                Pożegnaliśmy się! Maszyna agenta będzie pracować i wysyłać maile do końca aktualnego okresu rozliczeniowego: 
                <strong class="text-white bg-orange-500/20 text-orange-400 px-2 py-0.5 rounded ml-1 font-mono text-xs">{formatDate(data.cancelAtDate || data.currentPeriodEnd || '')}</strong>. 
                Po tej dacie instancja zostanie całkowicie wyparta z sieci.
              </p>
            {:else}
              <h2 class="text-2xl font-display font-bold text-red-500 tracking-tighter uppercase mb-2">Zawieszenie – Brak Płatności</h2>
              <p class="text-sm text-slate-400 leading-relaxed">
                Opłać najnowszą fakturę w Stripe, by agent NEXUS powrócił do cyklu operacyjnego.
              </p>
            {/if}
          </div>

          {#if data.status === 'active'}
            <button 
            onclick={requestCancel}
            disabled={isCanceling}
            class="shrink-0 flex items-center justify-center gap-2 px-8 py-3 rounded-2xl border border-red-500/20 text-red-500 font-display font-bold text-sm tracking-wider uppercase hover:border-red-500/50 hover:bg-red-500/10 transition-all focus:outline-none focus:border-red-500 disabled:opacity-50"
          >
            <span class="material-symbols-outlined text-lg">no_encryption</span>
            Wyłącz Agenta
          </button>
          {/if}

        </div>
      </div>
    </div>

    <!-- PRAWA KOLUMNA (FAKTURY) -->
    <div class="lg:col-span-4 rounded-3xl p-px bg-linear-to-b from-white/10 to-transparent flex flex-col h-full max-h-[800px]">
      <div class="bg-black/90 rounded-3xl backdrop-blur-xl flex flex-col overflow-hidden h-full relative">
        <div class="p-6 md:p-8 border-b border-white/5 relative z-10 shrink-0">
          <h2 class="text-[10px] font-mono uppercase tracking-widest text-slate-500 mb-2 flex items-center gap-2">
            <span class="material-symbols-outlined text-sm">receipt_long</span>
            Archiwum Rozliczeń
          </h2>
          <h3 class="text-xl font-display font-bold text-white uppercase tracking-tighter shadow-sm">Historia Faktur</h3>
        </div>
        
        <div class="flex-1 overflow-y-auto p-4 md:p-6 custom-scrollbar space-y-3 relative z-10 min-h-[300px]">
          {#if !data.payments || data.payments.length === 0}
            <div class="flex flex-col items-center justify-center h-full text-center space-y-4 opacity-50">
              <span class="material-symbols-outlined text-4xl text-slate-600">inventory_2</span>
              <p class="text-xs font-mono text-slate-500 uppercase tracking-widest">Pusty Rejestr</p>
            </div>
          {:else}
            {#each data.payments as payment (payment.id || payment.stripeInvoiceId)}
              <div class="group bg-white/5 hover:bg-white/10 border border-white/5 hover:border-white/20 rounded-2xl p-4 transition-all duration-300 relative overflow-hidden">
                <!-- Glowing border effect on hover -->
                <div class="absolute top-0 left-0 w-1 h-full opacity-0 group-hover:opacity-100 transition-opacity {payment.status === 'paid' ? 'bg-green-500' : 'bg-orange-500'}"></div>
                
                <div class="flex justify-between items-start mb-4">
                  <div>
                    <span class="block text-white font-display font-bold text-xl tracking-tight mb-1">{payment.amount} <span class="text-xs uppercase text-slate-500">PLN</span></span>
                    <span class="text-xs font-mono text-slate-500 tracking-wider"><span class="material-symbols-outlined text-[10px] align-middle mr-1">event</span>{formatDate(payment.paidAt)}</span>
                  </div>
                  <div class="shrink-0 px-2 py-1 rounded bg-black/50 border border-white/5 flex items-center gap-1.5">
                    <span class="w-1.5 h-1.5 rounded-full {payment.status === 'paid' ? 'bg-green-500' : 'bg-orange-500'}"></span>
                    <span class="text-[8px] font-mono uppercase tracking-widest {payment.status === 'paid' ? 'text-green-400' : 'text-orange-400'}">
                      {payment.status === 'paid' ? 'ZAPŁACONO' : 'OCZEKUJE'}
                    </span>
                  </div>
                </div>
                
                {#if payment.fakturaXlInvoiceId}
                  <a 
                    href={`/api/invoices/download?id=${payment.fakturaXlInvoiceId}`}
                    target="_blank"
                    class="w-full py-3 rounded-2xl font-display font-bold uppercase text-[10px] tracking-wider text-white transition-all duration-300 flex items-center justify-center gap-2 relative overflow-hidden group"
                    style="background: linear-gradient(135deg, hsl(270,60%,45%), hsl(280,70%,55%)); box-shadow: 0 0 20px hsl(270,60%,30%);"
                  >
                    <span class="absolute inset-0 w-full h-full bg-linear-to-b from-white/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none"></span>
                    <span class="material-symbols-outlined text-[14px]">download</span>
                    Pobierz PDF
                  </a>
                {:else}
                   <div class="flex items-center justify-center gap-2 w-full bg-slate-800/30 text-slate-500 font-mono text-[9px] uppercase tracking-widest font-bold py-3 px-4 rounded-xl border border-transparent">
                     <span class="material-symbols-outlined text-[12px] animate-spin">sync</span>
                     Wykulanie Faktury...
                   </div>
                {/if}
              </div>
            {/each}
          {/if}
        </div>
      </div>
    </div>
  </div>
{/if}

<!-- MODAL ANULOWANIA SUBSKRYPCJI -->
{#if showCancelConfirmModal}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md" onclick={() => showCancelConfirmModal = false}>
    <div class="rounded-3xl p-px bg-linear-to-b from-red-500/40 to-red-900/10 max-w-lg w-full relative z-10 shadow-[0_0_80px_rgba(239,68,68,0.15)] animate-in fade-in zoom-in duration-300">
      <div class="bg-black/95 rounded-3xl p-8 md:p-12 overflow-hidden" onclick={e => e.stopPropagation()}>
        <div class="absolute top-0 right-0 p-4 opacity-5 pointer-events-none">
          <span class="material-symbols-outlined" style="font-size: 150px;">warning</span>
        </div>
        
        <div class="flex items-center gap-4 mb-6 relative z-10">
          <div class="w-12 h-12 rounded-full bg-red-500/10 border border-red-500/30 flex items-center justify-center shrink-0">
            <span class="material-symbols-outlined text-red-500 text-xl">link_off</span>
          </div>
          <h2 class="text-2xl font-bold font-display uppercase tracking-tighter text-white drop-shadow-sm">Przetnij Połączenie</h2>
        </div>
        
        <div class="relative z-10 space-y-4 mb-10 text-slate-300 text-sm leading-relaxed">
          <p>Potwierdź deaktywację sztucznej inteligencji sprzedażowej. NEXUS przestanie prospectować dla Twojej firmy zaraz po wygaśnięciu Twojego cyklu rozliczeniowego.</p>
          <div class="bg-red-500/5 border border-red-500/10 p-4 rounded-xl text-red-300 text-xs font-mono uppercase tracking-widest">
            Twoja usługa pozostanie aktywna do <br/><strong class="text-white text-sm mt-1 block">końca obecnego cyklu</strong>.
          </div>
        </div>
        
        <div class="flex flex-col md:flex-row items-center gap-3 relative z-10">
        <button 
            onclick={() => showCancelConfirmModal = false}
            class="w-full md:w-auto px-8 py-4 rounded-2xl border border-white/10 text-slate-400 font-mono text-[10px] uppercase tracking-widest hover:border-primary/30 hover:text-primary transition-all disabled:opacity-50"
            disabled={isCanceling}
          >
            Anuluj akcję
          </button>
          <button 
            onclick={confirmCancel}
            disabled={isCanceling}
            class="w-full md:flex-1 py-4 rounded-2xl font-display font-bold uppercase tracking-wider text-sm text-white transition-all duration-300 disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-2 overflow-hidden relative group"
            style="background: linear-gradient(135deg, hsl(0,60%,45%), hsl(0,70%,55%)); box-shadow: 0 0 30px hsl(0,60%,30%);"
          >
            <span class="absolute inset-0 w-full h-full bg-linear-to-b from-white/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none"></span>
            {#if isCanceling}
              <span class="material-symbols-outlined text-sm animate-spin">sync</span>
              Przetwarzanie...
            {:else}
              Tak, Wyłącz Agenta
            {/if}
          </button>
        </div>
      </div>
    </div>
  </div>
{/if}

<!-- MODAL SUKCESU ANULOWANIA -->
{#if showCancelSuccessModal}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md" onclick={closeSuccessModal}>
    <div class="rounded-3xl p-px bg-linear-to-b from-orange-500/40 to-transparent max-w-lg w-full relative z-10 shadow-[0_0_80px_rgba(249,115,22,0.15)] animate-in fade-in zoom-in duration-300">
      <div class="bg-black/95 rounded-3xl p-8 md:p-12 overflow-hidden text-center" onclick={e => e.stopPropagation()}>
        <div class="absolute inset-x-0 top-0 h-32 bg-linear-to-b from-orange-500/10 to-transparent pointer-events-none"></div>
        
        <div class="relative z-10">
          <div class="w-20 h-20 rounded-full bg-orange-500/10 border border-orange-500/30 mx-auto flex items-center justify-center mb-6 shadow-[0_0_30px_rgba(249,115,22,0.2)]">
            <span class="material-symbols-outlined text-3xl text-orange-400">check</span>
          </div>
          
          <h2 class="text-2xl font-bold font-display uppercase tracking-tighter text-white mb-4 drop-shadow-sm">Proces Zakończony</h2>
          <p class="text-slate-400 text-sm mb-8 leading-relaxed">
            Zlecenie anulowania zostało zapisane, a powiadomienie e-mail wyleciało na Twoją skrzynkę.<br><br>
            Było wspaniale. Maszyna zostanie definitywnie odcięta w zaplanowanym terminie. W razie potrzeby – wiesz, gdzie nas znaleźć.
          </p>
          
          <button 
            onclick={closeSuccessModal}
            class="w-full py-4 rounded-2xl font-display font-bold uppercase tracking-wider text-sm text-white transition-all duration-300 flex items-center justify-center gap-2 overflow-hidden relative group mt-2"
            style="background: linear-gradient(135deg, hsl(270,60%,45%), hsl(280,70%,55%)); box-shadow: 0 0 30px hsl(270,60%,30%);"
          >
            <span class="absolute inset-0 w-full h-full bg-linear-to-b from-white/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none"></span>
            Zamknij i Odśwież Status
          </button>
        </div>
      </div>
    </div>
  </div>
{/if}

<style>
  .custom-scrollbar::-webkit-scrollbar {
    width: 6px;
  }
  .custom-scrollbar::-webkit-scrollbar-track {
    background: rgba(255, 255, 255, 0.02);
    border-radius: 8px;
  }
  .custom-scrollbar::-webkit-scrollbar-thumb {
    background: rgba(255, 255, 255, 0.1);
    border-radius: 8px;
  }
  .custom-scrollbar::-webkit-scrollbar-thumb:hover {
    background: rgba(168, 85, 247, 0.4);
  }
</style>
