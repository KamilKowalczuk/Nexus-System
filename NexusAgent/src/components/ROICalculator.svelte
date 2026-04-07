<script lang="ts">
  let { data }: { data?: any } = $props();

  let emailsPerDay = $state(20);

  // TITAN: 2,000 PLN/mo base for 20 emails/day, +25 PLN per extra email
  // (Exact pricing TBD - easy to adjust later)
  let titanCost = $derived(1999 + Math.max(0, emailsPerDay - 20) * 25);

  // SDR equivalent: 1 SDR handles ~20 emails/day and costs ~10,000 PLN/mo
  // More emails = need more SDR headcount
  let sdrEquivalent = $derived(Math.ceil(emailsPerDay / 20));
  let sdrCost = $derived(sdrEquivalent * 10000);
  let savings = $derived(sdrCost - titanCost);
  let savingsPercent = $derived(Math.round((savings / sdrCost) * 100));

  // Slider fill percentage for the track
  let fillPercent = $derived(((emailsPerDay - 10) / (100 - 10)) * 100);

  function handleSliderInput(e: Event) {
    emailsPerDay = parseInt((e.target as HTMLInputElement).value);
  }

  // Formatters with Payload Fallbacks
  let titleText = $derived(
    data?.title || "Kalkulator utraconego i odzyskanego przychodu",
  );

  let targetText = $derived(
    (data?.targetFormat ||
      "Cel wysyłki: {{count}} precyzyjnych maili dziennie")?.replace(
      "{{count}}",
      emailsPerDay.toString(),
    ),
  );

  let titanVsText = $derived(
    (data?.titanHeader ||
      "NEXUS vs {{count}} etatów SDR, które musiałbyś utrzymać")?.replace(
      "{{count}}",
      sdrEquivalent.toString(),
    ),
  );

  let sdrCostText = $derived(
    (data?.sdrCostFormat ||
      "Miesięczny koszt zespołu SDR: {{cost}} zł")?.replace(
      "{{cost}}",
      sdrCost.toLocaleString("pl-PL"),
    ),
  );

  let savingsText = $derived(
    (data?.savingsFormat ||
      "▲ Zatrzymujesz {{savings}} PLN miesięcznie zamiast oddawać je na pensje i prowizje ({{percent}}%)")
      ?.replace("{{savings}}", savings.toLocaleString("pl-PL"))
      .replace("{{percent}}", savingsPercent.toString()),
  );
</script>

<div class="flex flex-col md:flex-row items-center gap-12">
  <div class="w-full md:w-2/3">
    <div class="flex justify-between items-center mb-6">
      <h4 class="font-display text-xl font-bold uppercase">{titleText}</h4>
      <span class="font-mono text-primary text-sm font-bold tracking-tighter"
        >{targetText}</span
      >
    </div>
    <div class="relative">
      <input
        class="roi-slider w-full appearance-none bg-transparent cursor-pointer relative z-10"
        type="range"
        min="10"
        max="100"
        value={emailsPerDay}
        aria-label="Ilość maili dziennie"
        aria-valuemin={10}
        aria-valuemax={100}
        aria-valuenow={emailsPerDay}
        oninput={handleSliderInput}
      />
      <!-- Custom track background -->
      <div
        class="absolute top-1/2 left-0 right-0 h-[4px] -translate-y-1/2 rounded-full bg-white/10 pointer-events-none"
      >
        <div
          class="h-full rounded-full bg-primary/50 transition-all duration-150"
          style="width: {fillPercent}%;"
        ></div>
      </div>
    </div>
    <div
      class="flex justify-between text-[11px] text-slate-500 font-mono mt-4 uppercase tracking-widest"
    >
      <span>10 maili</span>
      <span>50 maili</span>
      <span>100 maili</span>
    </div>
  </div>
  <div
    class="text-center md:text-right border-l border-white/10 md:pl-12 shrink-0"
  >
    <div
      class="text-slate-500 text-[11px] font-mono uppercase mb-2 tracking-widest"
    >
      {titanVsText}
    </div>
    <div
      class="text-5xl font-display font-bold text-primary whitespace-nowrap"
      style="font-variant-numeric: tabular-nums;"
    >
      {titanCost.toLocaleString("pl-PL")} zł
    </div>
    <div
      class="text-[11px] text-slate-500 font-mono uppercase mt-1 whitespace-nowrap"
    >
      {sdrCostText}
    </div>
    <div
      class="text-[11px] text-green-400 font-mono uppercase mt-2 font-bold whitespace-nowrap"
    >
      {savingsText}
    </div>
  </div>
</div>
