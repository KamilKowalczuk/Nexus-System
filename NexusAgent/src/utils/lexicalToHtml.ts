export function renderLexical(node: any): string {
  if (!node) return '';

  if (node.type === 'text') {
    let text = escapeHtml(node.text || '');
    if (node.format & 1) text = `<strong>${text}</strong>`;
    if (node.format & 2) text = `<em>${text}</em>`;
    if (node.format & 8) text = `<u>${text}</u>`;
    return text;
  }

  if (node.type === 'paragraph') {
    const children = node.children?.map(renderLexical).join('') || '';
    // Empty paragraph can be a line break
    if (!children) return '<br/>';
    return `<p class="mb-5 leading-relaxed text-slate-400">${children}</p>`;
  }

  if (node.type === 'heading') {
    const children = node.children?.map(renderLexical).join('') || '';
    const tag = node.tag || 'h2';
    const classes =
      tag === 'h1' ? 'text-3xl md:text-5xl font-display font-bold mb-8 mt-12 text-white tracking-tight' :
      tag === 'h2' ? 'text-2xl md:text-3xl font-display font-bold mb-6 mt-10 text-white tracking-tight' :
      tag === 'h3' ? 'text-xl md:text-2xl font-display font-bold mb-4 mt-8 text-white' :
      'text-lg font-bold mt-6 mb-3 text-white';
    return `<${tag} class="${classes}">${children}</${tag}>`;
  }
  
  if (node.type === 'list') {
    const children = node.children?.map(renderLexical).join('') || '';
    const tag = node.listType === 'number' ? 'ol' : 'ul';
    const classes = tag === 'ol' 
      ? 'list-decimal mb-6 pl-5 space-y-2 text-slate-400 marker:text-primary' 
      : 'list-disc mb-6 pl-5 space-y-2 text-slate-400 marker:text-primary';
    return `<${tag} class="${classes}">${children}</${tag}>`;
  }

  if (node.type === 'listitem') {
    const children = node.children?.map(renderLexical).join('') || '';
    return `<li>${children}</li>`;
  }

  if (node.type === 'quote') {
    const children = node.children?.map(renderLexical).join('') || '';
    return `<blockquote class="border-l-2 border-primary pl-6 py-2 italic my-8 text-slate-300 bg-white/5 rounded-r-lg">${children}</blockquote>`;
  }

  if (node.type === 'link' || node.type === 'autolink') {
    const children = node.children?.map(renderLexical).join('') || '';
    const url = node.fields?.url || node.url || '#';
    const newTab = node.fields?.newTab ? ' target="_blank" rel="noopener noreferrer"' : '';
    return `<a href="${url}" class="text-primary hover:text-white transition-colors duration-300 underline underline-offset-4 decoration-primary/30 hover:decoration-primary"${newTab}>${children}</a>`;
  }

  if (node.type === 'upload') {
    return `<!-- image upload not supported natively in simple legal docs yet -->`;
  }

  // Fallback for root or unknown blocks with children
  if (node.children) {
    return node.children.map(renderLexical).join('');
  }

  return '';
}

function escapeHtml(unsafe: string): string {
  return unsafe
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
