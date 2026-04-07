/**
 * reportPdf.ts
 * ────────────────────────────────────────────────────────────────────
 * Premium PDF Report Generator — NEXUS Agent Campaign Statistics
 *
 * Design: Dark theme (#0a0a0f), Cyan (#0ceaed) + Purple (#a855f7) accents
 * Fonts: Roboto (Regular/Bold) with Helvetica fallback
 * ────────────────────────────────────────────────────────────────────
 */

import PDFDocument from 'pdfkit';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';
import type { AllTimeStats, DailyStats, WeekComparison } from './campaignStats';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const publicDir = path.resolve(__dirname, '../../public');

// ─── Design Tokens ──────────────────────────────────────────────────────
const C = {
  bg: '#0a0a0f',
  cardBg: '#111118',
  cardBorder: '#1e293b',
  cyan: '#0ceaed',
  purple: '#a855f7',
  green: '#22c55e',
  amber: '#f59e0b',
  red: '#ef4444',
  white: '#ffffff',
  text: '#e2e8f0',
  textMuted: '#94a3b8',
  textDim: '#64748b',
  divider: '#1e293b',
} as const;

const PAGE_W = 595;
const PAGE_H = 842;
const M = { left: 40, right: 40, top: 40, bottom: 30 };
const CONTENT_W = PAGE_W - M.left - M.right;

interface ReportData {
  companyName: string;
  orderNumber: string;
  dailyLimit: number;
  monthlyAmount: number;
  summary: AllTimeStats;
  dailyStats: DailyStats[];
  weekComparison: WeekComparison;
  reportPeriod: string; // e.g. "06.03 – 05.04.2026"
}

export async function generateReportPdf(data: ReportData): Promise<Buffer> {
  // ─── Font loading ───
  const robotoRegularPath = path.join(publicDir, 'fonts', 'Roboto-Regular.ttf');
  const robotoBoldPath = path.join(publicDir, 'fonts', 'Roboto-Bold.ttf');
  const siteUrl = 'https://nexusagent.pl';

  let hasRoboto = false;
  let regBuf: Buffer | null = null;
  let boldBuf: Buffer | null = null;

  try {
    if (fs.existsSync(robotoRegularPath) && fs.existsSync(robotoBoldPath)) {
      regBuf = fs.readFileSync(robotoRegularPath);
      boldBuf = fs.readFileSync(robotoBoldPath);
      hasRoboto = true;
    } else {
      const [regRes, boldRes] = await Promise.all([
        fetch(`${siteUrl}/fonts/Roboto-Regular.ttf`),
        fetch(`${siteUrl}/fonts/Roboto-Bold.ttf`)
      ]);
      if (regRes.ok && boldRes.ok) {
        regBuf = Buffer.from(await regRes.arrayBuffer());
        boldBuf = Buffer.from(await boldRes.arrayBuffer());
        hasRoboto = true;
      }
    }
  } catch {
    console.warn('[ReportPDF] Font Roboto load failed, using Helvetica fallback.');
  }

  // ─── Logo ───
  const logoPath = path.join(publicDir, 'logo.png');
  let logoBuf: Buffer | null = null;
  try {
    if (fs.existsSync(logoPath)) {
      logoBuf = fs.readFileSync(logoPath);
    } else {
      const logoRes = await fetch(`${siteUrl}/logo.png`);
      if (logoRes.ok) logoBuf = Buffer.from(await logoRes.arrayBuffer());
    }
  } catch {
    console.warn('[ReportPDF] Logo load failed, skipping.');
  }

  return new Promise((resolve, reject) => {
    const doc = new PDFDocument({
      margins: { top: M.top, bottom: M.bottom, left: M.left, right: M.right },
      size: 'A4',
      bufferPages: true,
    });

    const chunks: Buffer[] = [];
    doc.on('data', (chunk: Buffer) => chunks.push(chunk));
    doc.on('end', () => resolve(Buffer.concat(chunks)));
    doc.on('error', reject);

    if (hasRoboto && regBuf && boldBuf) {
      doc.registerFont('Roboto', regBuf);
      doc.registerFont('Roboto-Bold', boldBuf);
    }

    const F = hasRoboto ? 'Roboto' : 'Helvetica';
    const FB = hasRoboto ? 'Roboto-Bold' : 'Helvetica-Bold';

    // ─── Efficient Dark Background ───
    const drawBg = () => {
      doc.rect(0, 0, PAGE_W, PAGE_H).fill(C.bg);
    };
    
    doc.on('pageAdded', drawBg);
    drawBg(); // First page

    const ensureSpace = (needed: number) => {
      // Use a slightly larger margin to avoid edge cases at bottom of pages
      if (doc.y + needed > PAGE_H - M.bottom - 5) {
        doc.addPage();
        doc.y = M.top + 5;
      }
    };

    const sectionHeader = (title: string, icon?: string) => {
      ensureSpace(40);
      doc.moveDown(0.8);
      doc.fontSize(7).fillColor(C.cyan).font(F)
        .text(`${icon ? icon + '  ' : ''}${title.toUpperCase()}`, M.left, doc.y, { characterSpacing: 2.5 });
      doc.moveTo(M.left, doc.y + 3).lineTo(M.left + CONTENT_W, doc.y + 3)
        .strokeColor(C.divider).lineWidth(0.5).stroke();
      doc.moveDown(0.6);
    };

    const kpiCard = (x: number, y: number, w: number, h: number, value: string, label: string, color: string) => {
      // Card background
      doc.roundedRect(x, y, w, h, 6).fill(C.cardBg);
      doc.roundedRect(x, y, w, h, 6).strokeColor(C.cardBorder).lineWidth(0.5).stroke();

      // Accent bar top
      doc.rect(x + 1, y + 1, w - 2, 2.5).fill(color);

      // Value
      doc.fontSize(20).fillColor(C.white).font(FB)
        .text(value, x + 10, y + 14, { width: w - 20, align: 'center' });

      // Label
      doc.fontSize(6.5).fillColor(C.textDim).font(F)
        .text(label.toUpperCase(), x + 6, y + h - 16, { width: w - 12, align: 'center', characterSpacing: 1 });
    };

    // Format helpers
    const fmt = (n: any) => Number(n ?? 0).toLocaleString('pl-PL');
    const fmtPct = (n: any) => `${Number(n ?? 0).toFixed(1)}%`;

    // ═══════════════════════════════════════════════════════════════════
    // PAGE 1: HEADER + EXECUTIVE SUMMARY
    // ═══════════════════════════════════════════════════════════════════

    // ─── Logo + Header ───
    let headerY = 35;
    if (logoBuf) {
      doc.image(logoBuf, PAGE_W / 2 - 35, headerY, { width: 70, height: 70 });
      headerY += 78;
    }

    doc.fontSize(6.5).fillColor(C.cyan).font(F)
      .text('NEXUS AGENT · RAPORT KAMPANII · POUFNE', M.left, headerY, { align: 'center', characterSpacing: 3 });
    headerY += 16;

    doc.fontSize(22).fillColor(C.white).font(FB)
      .text('RAPORT KAMPANII', M.left, headerY, { align: 'center' });
    headerY += 28;

    doc.fontSize(13).fillColor(C.purple).font(FB)
      .text(data.companyName.toUpperCase(), M.left, headerY, { align: 'center' });
    headerY += 22;

    doc.fontSize(8).fillColor(C.textMuted).font(F)
      .text(`Okres: ${data.reportPeriod}  ·  Zamówienie: ${data.orderNumber}`, M.left, headerY, { align: 'center' });
    headerY += 14;

    doc.fontSize(7).fillColor(C.textDim).font(F)
      .text(`Plan: ${data.dailyLimit} maili/dzień  ·  ${data.monthlyAmount.toLocaleString('pl-PL')} PLN/mc`, M.left, headerY, { align: 'center' });
    headerY += 6;

    doc.moveTo(M.left, headerY + 8).lineTo(M.left + CONTENT_W, headerY + 8)
      .strokeColor(C.purple).lineWidth(1).stroke();

    doc.y = headerY + 25;

    // ─── EXECUTIVE SUMMARY — KPI Cards (2 rows × 4) ───
    sectionHeader('Podsumowanie Kampanii', '>>');

    const s = data.summary;
    const cardW = (CONTENT_W - 30) / 4;
    const cardH = 58;
    const cardGap = 10;
    let cardY = doc.y;

    // Row 1: Core KPIs
    kpiCard(M.left, cardY, cardW, cardH, fmt(s.total_first_touch), 'Wysłane Maile', C.cyan);
    kpiCard(M.left + cardW + cardGap, cardY, cardW, cardH, fmt(s.total_replies), 'Odpowiedzi', C.purple);
    kpiCard(M.left + (cardW + cardGap) * 2, cardY, cardW, cardH, fmt(s.hot_leads), 'Gorące Leady', C.green);
    kpiCard(M.left + (cardW + cardGap) * 3, cardY, cardW, cardH, fmtPct(s.reply_rate), 'Wskaźnik ODP.', C.amber);

    cardY += cardH + cardGap;

    // Row 2: Pipeline KPIs
    kpiCard(M.left, cardY, cardW, cardH, fmt(s.total_scanned), 'Skanowanie Rynku', C.cyan);
    kpiCard(M.left + cardW + cardGap, cardY, cardW, cardH, fmt(s.total_qualified), 'Zakwalifikowane', C.green);
    kpiCard(M.left + (cardW + cardGap) * 2, cardY, cardW, cardH, fmt(s.total_delivery), 'Dostarczone', C.purple);
    kpiCard(M.left + (cardW + cardGap) * 3, cardY, cardW, cardH, fmtPct(s.positive_rate), 'Skuteczność ODP.', C.green);

    doc.y = cardY + cardH + 10;

    // ─── Week-over-Week Comparison ───
    sectionHeader('Trend Tygodniowy', '>>');

    const wk = data.weekComparison;
    const trendRow = (label: string, thisW: number, lastW: number, x: number, y: number) => {
      const change = lastW > 0 ? ((thisW - lastW) / lastW * 100) : (thisW > 0 ? 100 : 0);
      const arrow = change > 0 ? '+' : change < 0 ? '-' : '=';
      const color = change > 0 ? C.green : change < 0 ? C.red : C.textDim;

      doc.fontSize(7).fillColor(C.textDim).font(F).text(label.toUpperCase(), x, y, { characterSpacing: 1 });
      doc.fontSize(16).fillColor(C.white).font(FB).text(fmt(thisW), x, y + 11);
      doc.fontSize(7).fillColor(color).font(F).text(`${arrow} ${Math.abs(change).toFixed(0)}% vs ${fmt(lastW)} (tydzień wcześniej)`, x, y + 30);
    };

    const trendY = doc.y;
    const trendColW = CONTENT_W / 3;
    trendRow('Wysłane', wk.this_week.sent, wk.last_week.sent, M.left, trendY);
    trendRow('Odpowiedzi', wk.this_week.replies, wk.last_week.replies, M.left + trendColW, trendY);
    trendRow('Gorące Leady', wk.this_week.hot_leads, wk.last_week.hot_leads, M.left + trendColW * 2, trendY);

    doc.y = trendY + 50;

    // ─── Detailed Metrics ───
    sectionHeader('Szczegółowe Metryki', '[+]');

    const metricRow = (label: string, value: string, color?: string) => {
      ensureSpace(14);
      const y = doc.y;
      doc.fontSize(8).fillColor(C.textMuted).font(F).text(label, M.left + 10, y);
      doc.fontSize(8.5).fillColor(color || C.white).font(FB).text(value, M.left + CONTENT_W - 150, y, { width: 140, align: 'right' });
      doc.moveTo(M.left + 10, y + 14).lineTo(M.left + CONTENT_W - 10, y + 14)
        .strokeColor('#0f172a').lineWidth(0.4).stroke();
      doc.y = y + 18;
    };

    // Scouting
    doc.fontSize(7).fillColor(C.cyan).font(F).text('SKANOWANIE RYNKU', M.left, doc.y, { characterSpacing: 2 });
    doc.moveDown(0.3);
    metricRow('Przeskanowane domeny', fmt(s.total_scanned));
    metricRow('Zakwalifikowane firmy', fmt(s.total_qualified), C.green);
    metricRow('Trafność skanowania', fmtPct(s.scout_approval_rate), C.cyan);

    doc.moveDown(0.5);
    doc.fontSize(7).fillColor(C.cyan).font(F).text('ANALIZA KONTAKTÓW', M.left, doc.y, { characterSpacing: 2 });
    doc.moveDown(0.3);
    metricRow('Znalezione kontakty', fmt(s.total_emails_found));
    metricRow('Zweryfikowane kontakty', fmt(s.total_emails_verified), C.green);
    metricRow('Jakość kontaktów', fmtPct(s.email_verification_rate), C.cyan);

    doc.moveDown(0.5);
    doc.fontSize(7).fillColor(C.cyan).font(F).text('WYSYŁKA I DOSTARCZANIE', M.left, doc.y, { characterSpacing: 2 });
    doc.moveDown(0.3);
    metricRow('First-touch maile', fmt(s.total_first_touch));
    metricRow('Follow-up #2', fmt(s.total_followup2));
    metricRow('Follow-up #3', fmt(s.total_followup3));
    metricRow('Łącznie dostarczono', fmt(s.total_delivery), C.green);
    metricRow('Bounce rate', fmtPct(s.bounce_rate), Number(s.bounce_rate) < 5 ? C.green : C.amber);

    doc.moveDown(0.5);
    doc.fontSize(7).fillColor(C.cyan).font(F).text('ANGAŻOWANIE ODBIORCÓW', M.left, doc.y, { characterSpacing: 2 });
    doc.moveDown(0.3);
    metricRow('Odpowiedzi łącznie', fmt(s.total_replies));
    metricRow('Gorące leady (pozytywne)', fmt(s.hot_leads), C.green);
    metricRow('Wskaźnik ODP. (Reply rate)', fmtPct(s.reply_rate), Number(s.reply_rate) >= 5 ? C.green : C.amber);
    metricRow('Skuteczność ODP. (Lead gen)', fmtPct(s.positive_rate), C.green);
    metricRow('Wypisania (Opt-out)', fmt(s.total_optouts), Number(s.total_optouts) > 10 ? C.amber : C.textMuted);
    metricRow('Średni czas odpowiedzi', `${s.avg_response_hours || 0}h`, C.cyan);

    doc.moveDown(0.3);
    doc.fontSize(7).fillColor(C.cyan).font(F).text('JAKOŚĆ AI', M.left, doc.y, { characterSpacing: 2 });
    doc.moveDown(0.3);
    metricRow('Wygenerowane wiadomości', fmt(s.total_drafted));
    metricRow('Jakość treści AI', `${s.avg_ai_quality || 0}/100`, Number(s.avg_ai_quality) >= 70 ? C.green : C.amber);

    // ═══════════════════════════════════════════════════════════════════
    // PAGE 2+: DAILY BREAKDOWN CHART + TABLE
    // ═══════════════════════════════════════════════════════════════════

    if (data.dailyStats.length > 0) {
      ensureSpace(150);
      doc.moveDown(0.5);

      sectionHeader('Dzienna Aktywność (30 Dni)', '>>');
      doc.moveDown(1.5);

      // ─── Mini bar chart (emails_sent + replies) ───
      const chartX = M.left + 5;
      const chartW = CONTENT_W - 10;
      const chartH = 80;
      const chartY = doc.y + 10;
      const days = data.dailyStats.slice(-30);
      const maxVal = Math.max(...days.map(d => d.emails_sent), 1);
      
      const chartInnerX = chartX + 30;
      const chartInnerW = chartW - 40;
      const gap = 2;
      const barW = (chartInnerW - (days.length * gap)) / days.length;

      // Chart background
      doc.roundedRect(chartX, chartY - 10, chartW, chartH + 35, 6).fill(C.cardBg);
      doc.roundedRect(chartX, chartY - 10, chartW, chartH + 35, 6)
        .strokeColor(C.cardBorder).lineWidth(0.5).stroke();

      // Grid lines
      for (let i = 0; i <= 4; i++) {
        const gy = chartY + chartH - (chartH / 4) * i;
        doc.moveTo(chartInnerX, gy).lineTo(chartInnerX + chartInnerW, gy)
          .strokeColor('#1e293b').lineWidth(0.3).stroke();
        doc.fontSize(5).fillColor(C.textDim).font(F)
          .text(Math.round(maxVal / 4 * i).toString(), chartX + 2, gy - 2, { width: 25, align: 'right' });
      }

      // Bars
      days.forEach((day, i) => {
        const bx = chartInnerX + i * (barW + gap) + gap/2;
        const sentH = (day.emails_sent / maxVal) * chartH;
        const repliesH = (day.replies_total / maxVal) * chartH;

        if (sentH > 0) {
          doc.rect(bx, chartY + chartH - sentH, barW * 0.7, sentH).fill(C.cyan);
        }
        if (repliesH > 0) {
          doc.rect(bx + barW * 0.3, chartY + chartH - repliesH, barW * 0.7, repliesH).fill(C.purple);
        }
      });

      // Legend
      const legendY = chartY + chartH + 10;
      doc.rect(chartInnerX, legendY, 6, 6).fill(C.cyan);
      doc.fontSize(6).fillColor(C.textDim).font(F).text('Wysłane', chartInnerX + 10, legendY);
      doc.rect(chartInnerX + 60, legendY, 6, 6).fill(C.purple);
      doc.fontSize(6).fillColor(C.textDim).font(F).text('Odpowiedzi', chartInnerX + 70, legendY);

      doc.y = legendY + 15;

      // ─── Data Table ───
      ensureSpace(80);
      sectionHeader('Szczegółowy Wykaz Dzienny', '>>');

      const cols = [
        { label: 'DATA', w: 60, align: 'left' as const },
        { label: 'SKAN.', w: 40, align: 'right' as const },
        { label: 'WYSŁ.', w: 40, align: 'right' as const },
        { label: 'FU#2', w: 35, align: 'right' as const },
        { label: 'FU#3', w: 35, align: 'right' as const },
        { label: 'ODP.', w: 40, align: 'right' as const },
        { label: 'LEADY', w: 35, align: 'right' as const },
        { label: '% ODP.', w: 40, align: 'right' as const },
        { label: 'ODRZUC.', w: 40, align: 'right' as const },
        { label: 'AI', w: 35, align: 'right' as const },
      ];

      let tableX = M.left;
      const rowH = 12;

      // Header row
      ensureSpace(20);
      const headY = doc.y;
      doc.rect(tableX, headY, CONTENT_W, rowH + 2).fill('#0f172a');
      let colX = tableX + 4;
      cols.forEach(col => {
        doc.fontSize(5).fillColor(C.cyan).font(FB)
          .text(col.label, colX, headY + 3, { width: col.w, align: col.align, characterSpacing: 0.8 });
        colX += col.w;
      });

      doc.y = headY + rowH + 4;

      // Data rows (reversed → newest first)
      const reversedDays = [...days].reverse();
      reversedDays.forEach((day, idx) => {
        ensureSpace(rowH);
        const ry = doc.y;

        if (idx % 2 === 0) {
          doc.rect(tableX, ry, CONTENT_W, rowH).fill('#0d0d14');
        }

        let cx = tableX + 4;
        const dateStr = new Date(day.date).toLocaleDateString('pl-PL', { day: '2-digit', month: '2-digit' });
        const rowData = [
          dateStr,
          fmt(day.domains_scanned),
          fmt(day.emails_sent),
          fmt(day.followup_step_2_sent),
          fmt(day.followup_step_3_sent),
          fmt(day.replies_total),
          fmt(day.replies_positive),
          `${Number(day.reply_rate).toFixed(1)}%`,
          fmt(day.bounces),
          Number(day.avg_confidence_score).toFixed(0),
        ];

        rowData.forEach((val, vi) => {
          let color: string = C.text;
          if (vi === 6 && Number(val) > 0) color = C.green; // hot leads
          if (vi === 7) {
            const rate = parseFloat(val);
            color = rate >= 5 ? C.green : rate > 0 ? C.amber : C.textDim;
          }
          doc.fontSize(6).fillColor(color).font(F)
            .text(val, cx, ry + 2.5, { width: cols[vi].w, align: cols[vi].align });
          cx += cols[vi].w;
        });

        doc.y = ry + rowH;
      });
    }

    // ═══════════════════════════════════════════════════════════════════
    // INSIGHTS & FOOTER
    // ═══════════════════════════════════════════════════════════════════
    ensureSpace(60);
    doc.moveDown(0.5);
    sectionHeader('Analiza i Rekomendacje', '[!]');

    const insights: string[] = [];
    const s2 = data.summary;

    if (Number(s2.reply_rate) >= 10) {
      insights.push(`[+]  Wskaźnik odpowiedzi ${fmtPct(s2.reply_rate)} — doskonały wynik. Benchmark B2B cold email to 5-15%. Twoja kampania działa powyżej normy.`);
    } else if (Number(s2.reply_rate) >= 5) {
      insights.push(`[+]  Wskaźnik odpowiedzi ${fmtPct(s2.reply_rate)} — solidny wynik w normie rynkowej (benchmark: 5-15%). System pracuje stabilnie.`);
    } else if (Number(s2.reply_rate) > 0) {
      insights.push(`[!]  Wskaźnik odpowiedzi ${fmtPct(s2.reply_rate)} — poniżej benchmarku. Optymalizujemy personalizację i timing wysyłki.`);
    }

    if (Number(s2.positive_rate) >= 40) {
      insights.push(`[+]  ${fmtPct(s2.positive_rate)} odpowiedzi to gorące leady — wyjątkowo wysoka jakość konwersji.`);
    }

    if (Number(s2.bounce_rate) < 3) {
      insights.push(`[+]  Bounce rate ${fmtPct(s2.bounce_rate)} — doskonała higiena bazy kontaktów. Domena jest bezpieczna.`);
    } else if (Number(s2.bounce_rate) >= 5) {
      insights.push(`[!]  Bounce rate ${fmtPct(s2.bounce_rate)} — monitorujemy. Wzmocnienie weryfikacji DeBounce w toku.`);
    }

    if (Number(s2.avg_ai_quality) >= 75) {
      insights.push(`[+]  Jakość treści AI: ${s2.avg_ai_quality}/100 — wiadomości brzmią naturalnie i trafnie.`);
    }

    if (Number(s2.scout_approval_rate) > 0) {
      insights.push(`[i]  Trafność skanowania: ${fmtPct(s2.scout_approval_rate)} — AI skutecznie filtruje firmy pasujące do Twojego ICP.`);
    }

    if (s2.hot_leads > 0) {
      insights.push(`[!]  ${s2.hot_leads} gorących leadów czeka na domknięcie. Sprawdź odpowiedzi w skrzynce.`);
    }

    if (insights.length === 0) {
      insights.push(`[i]  Kampania jest w fazie startu. Kumulujemy dane — szczegółowa analiza w kolejnym raporcie.`);
    }

    insights.forEach(insight => {
      ensureSpace(20);
      doc.fontSize(7.5).fillColor(C.text).font(F)
        .text(insight, M.left + 10, doc.y, { width: CONTENT_W - 20, lineGap: 3 });
      doc.moveDown(0.3);
    });

    // ─── Security badge ───
    ensureSpace(50);
    doc.moveDown(1.5);
    const badgeY = doc.y;
    const badgeH = 45;
    doc.roundedRect(M.left, badgeY, CONTENT_W, badgeH, 6).fill('#0f0f1a');
    doc.roundedRect(M.left, badgeY, CONTENT_W, badgeH, 6).strokeColor(C.purple + '40').lineWidth(0.5).stroke();
    
    doc.fontSize(6).fillColor(C.purple).font(FB)
      .text('[#]  PROTOKÓŁ BEZPIECZEŃSTWA', M.left + 14, badgeY + 11, { characterSpacing: 1.5 });
      
    doc.fontSize(6.5).fillColor(C.textDim).font(F)
      .text('Ten raport został wygenerowany systemowo przez NEXUS Agent. Dane są poufne i przeznaczone wyłącznie dla odbiorcy. Wszystkie wrażliwe dane uwierzytelniające są zabezpieczone przez standardy Google Cloud KMS.',
        M.left + 14, badgeY + 22, { width: CONTENT_W - 28, lineGap: 1.5 });

    // ─── Footer on every page ───
    const pages = doc.bufferedPageRange();
    const totalPages = pages.start + pages.count;
    for (let i = pages.start; i < totalPages; i++) {
      doc.switchToPage(i);
      // Safe zone check: PAGE_H - M.bottom (842 - 30 = 812). Placing at 807.
      doc.fontSize(5.5).fillColor(C.textDim).font(F)
        .text(
          `Wygenerowano: ${new Date().toLocaleString('pl-PL')}  ·  NEXUS AGENT  ·  nexusagent.pl  ·  Strona ${i + 1}/${totalPages}`,
          M.left, PAGE_H - 35,
          { align: 'center', width: CONTENT_W }
        );
    }

    doc.end();
  });
}
