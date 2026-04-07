<script lang="ts">
  let { href = "#", text = "Action", type = "cyan" } = $props();

  // svelte-ignore state_referenced_locally
  const glowClass =
    type === "cyan"
      ? "neon-glow-cyan text-titan-cyan border-titan-cyan"
      : "neon-glow-purple text-titan-purple border-titan-purple";
  const glitchHoverObj =
    "signature-glitch group-hover:animate-[staticNoise_0.2s_infinite]";
</script>

<a
  {href}
  class="relative inline-flex items-center justify-center px-8 py-4 font-space font-bold uppercase tracking-widest text-sm rounded-lg border transition-all duration-300 group hover:scale-105 {glowClass}"
>
  <span class="relative z-10">{text}</span>

  <!-- Overlay glow effect -->
  <div
    class="absolute inset-0 bg-current opacity-10 blur-md rounded-lg group-hover:opacity-30 transition-opacity"
  ></div>

  <!-- Micro glitch element -->
  <span
    class="absolute top-0 right-[-4px] w-1 h-2 bg-current opacity-0 {glitchHoverObj} transition-opacity duration-75"
  ></span>
  <span
    class="absolute bottom-0 left-[-4px] w-1 h-3 bg-current opacity-0 {glitchHoverObj} transition-opacity duration-75 delay-75"
  ></span>
</a>
