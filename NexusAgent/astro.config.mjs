// @ts-check
import { defineConfig } from 'astro/config';
import svelte from '@astrojs/svelte';
import tailwindcss from '@tailwindcss/vite';
import netlify from '@astrojs/netlify';
import sitemap from '@astrojs/sitemap';

// https://astro.build/config
export default defineConfig({
  site: 'https://nexusagent.pl',
  adapter: netlify(),
  integrations: [svelte(), sitemap()],
  build: {
    // Wbuduj CSS inline w HTML zamiast osobnych plików blokujących render
    // Eliminuje render-blocking /_astro/*.css (główna przyczyna FCP 5s)
    inlineStylesheets: 'always',
  },
  vite: {
    plugins: [tailwindcss()]
  }
});