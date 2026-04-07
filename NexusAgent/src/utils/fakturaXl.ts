/**
 * fakturaXl.ts – Klient API Faktura XL (XML) dla NEXUS Agent
 *
 * Zmienne środowiskowe wymagane:
 *   FAKTURA_XL_API_TOKEN – produkcyjny token API konta Faktura XL
 */

export interface FakturaXlClientData {
  companyName: string;
  firstName?: string;
  lastName?: string;
  email: string;
  taxNo?: string; // NIP
  street?: string;
  city?: string;
  postCode?: string;
  country?: string;
  phone?: string;
}

export interface FakturaXlInvoiceParams {
  client: FakturaXlClientData;
  orderNumber: string; // Używane w opisie
  serviceName: string; // np. "NEXUS Agent – 20 maili/dzień – Plan miesięczny"
  totalPriceGross: number; // kwota brutto w PLN
  taxRate?: number | string; // stawka VAT (np. 23, 'zw')
  issueDateOverride?: string; // (YYYY-MM-DD) opcjonalne nadpisanie
  isVatExempt?: boolean; // Czy firma jest zwolniona z VAT (Rachunek)
  vatExemptionBasis?: string; // Opcjonalna podstawa prawna do wyświetlenia na fakturze (np. art. 113 ust. 1 i 9)
}

export interface FakturaXlInvoiceResult {
  id: number;
}

// ─── Pomocniki ───────────────────────────────────────────────────────────────

function getToken(): string {
  const token = import.meta.env.FAKTURA_XL_API_TOKEN;
  if (!token) throw new Error('[Faktura XL] Brak FAKTURA_XL_API_TOKEN w .env');
  return token;
}

function todayISO(): string {
  return new Date().toISOString().split('T')[0];
}

// Zabezpieczenie przed znakami specjalnymi w XML
function escapeXml(unsafe: string): string {
  if (!unsafe) return '';
  return unsafe.replace(/[<>&'"]/g, (c) => {
    switch (c) {
      case '<': return '&lt;';
      case '>': return '&gt;';
      case '&': return '&amp;';
      case "'": return '&apos;';
      case '"': return '&quot;';
      default: return c;
    }
  });
}

function parseXmlTag(xml: string, tag: string): string | null {
  const regex = new RegExp(`<${tag}>([^<]+)</${tag}>`, 'i');
  const match = xml.match(regex);
  return match && match[1] ? match[1].trim() : null;
}

// ─── 1. Utwórz dokument (Faktura) ───────────────────────────────────────────

export async function createInvoice(
  params: FakturaXlInvoiceParams
): Promise<FakturaXlInvoiceResult | null> {
  const token = getToken();
  const issueDate = params.issueDateOverride || todayISO();
  const taxRate = params.taxRate ?? 23;

  const url = 'https://program.fakturaxl.pl/api/dokument_dodaj.php';

  // Obliczenie ceny netto (przy założeniu kwoty brutto wliczonej).
  // XL wspiera podawanie brutto, jeśli w XML ustawimy 'oblicz_od' = 'brutto'
  const grossAmount = params.totalPriceGross.toFixed(2);
  const qty = 1;

  // Tworzymy XML zgodnie z dokumentacją Faktura XL
  // 0 – Faktura VAT
  const requestXml = `<?xml version="1.0" encoding="UTF-8"?>
<dokument>
    <api_token>${escapeXml(token)}</api_token>
    <typ_faktury>${params.isVatExempt ? '6' : '0'}</typ_faktury>
    <obliczaj_sume_wartosci_faktury_wg>0</obliczaj_sume_wartosci_faktury_wg>
    <data_wystawienia>${issueDate}</data_wystawienia>
    <data_sprzedazy>${issueDate}</data_sprzedazy>
    <rodzaj_platnosci>Przelew</rodzaj_platnosci>
    <waluta>PLN</waluta>
    <status>2</status> <!-- 2 = Opłacona (wg API docs) -->
    ${params.vatExemptionBasis ? `<uwagi>${escapeXml(params.vatExemptionBasis)}</uwagi>` : ''}
    
    <faktura_pozycje>
        <nazwa>${escapeXml(params.serviceName)} - Zamówienie: ${escapeXml(params.orderNumber)}</nazwa>
        <ilosc>${qty}</ilosc>
        <jm>szt.</jm>
        <vat>${params.isVatExempt ? 'zw' : taxRate}</vat>
        <wartosc_brutto>${grossAmount}</wartosc_brutto>
    </faktura_pozycje>

    <!-- Dane nabywcy -->
    <nabywca>
        <firma_lub_osoba_prywatna>${params.client.taxNo ? '0' : '1'}</firma_lub_osoba_prywatna>
        <nazwa>${escapeXml(params.client.companyName)}</nazwa>
        <imie>${escapeXml(params.client.firstName || '')}</imie>
        <nazwisko>${escapeXml(params.client.lastName || '')}</nazwisko>
        <nip>${escapeXml(params.client.taxNo || '')}</nip>
        <ulica_i_numer>${escapeXml(params.client.street || '')}</ulica_i_numer>
        <kod_pocztowy>${escapeXml(params.client.postCode || '')}</kod_pocztowy>
        <miejscowosc>${escapeXml(params.client.city || '')}</miejscowosc>
        <kraj>${escapeXml(params.client.country || 'PL')}</kraj>
        <email>${escapeXml(params.client.email)}</email>
        <telefon>${escapeXml(params.client.phone || '')}</telefon>
    </nabywca>
    <jezyk>0</jezyk>
    <wyslij_dokument_do_klienta_emailem>0</wyslij_dokument_do_klienta_emailem> 
</dokument>`;

  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/xml; charset=utf-8',
        'Accept': 'application/xml',
      },
      body: requestXml,
    });

    const responseText = await res.text();

    if (!res.ok) {
      console.error('[Faktura XL] Błąd tworzenia faktury. Status:', res.status, responseText);
      return null;
    }

    // Próba odczytu <dokument_id> wygenerowanego dokumentu z odpowiedzi XML
    const dokumentIdStr = parseXmlTag(responseText, 'dokument_id');
    const dokumentId = dokumentIdStr ? parseInt(dokumentIdStr, 10) : null;

    if (!dokumentId || isNaN(dokumentId)) {
      console.error('[Faktura XL] Nie odnaleziono poprawnego <dokument_id> w odpowiedzi:', responseText);
      return null;
    }

    return { id: dokumentId };
  } catch (err) {
    console.error('[Faktura XL] createInvoice Exception:', err);
    return null;
  }
}

// ─── 2. Pobierz PDF faktury (dołączenie do emaila) ──────────────────────────

/**
 * Endpoint `pdf_p.php` zwraca zawartość PDF w tagu `<pdf>` jako tekst Base64.
 * Funkcja zwraca Buffer gotowy do wrzucenia np. jako załącznik do Resend.
 */
export async function downloadInvoicePdf(dokumentId: number): Promise<Buffer | null> {
  const token = getToken();
  const url = 'https://program.fakturaxl.pl/api/pdf_p.php';

  const requestXml = `<?xml version="1.0" encoding="UTF-8"?>
<dokument>
    <api_token>${escapeXml(token)}</api_token>
    <dokument_id>${dokumentId}</dokument_id>
</dokument>`;

  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/xml; charset=utf-8',
        'Accept': 'application/xml',
      },
      body: requestXml,
    });

    const responseText = await res.text();

    if (!res.ok) {
      console.error('[Faktura XL] Błąd pobierania PDF-a. Status:', res.status, responseText);
      return null;
    }

    // Zgodnie z doc wpis ukryty jest w znaczniku <pdf> w Base64
    const base64Data = parseXmlTag(responseText, 'pdf');

    if (!base64Data) {
      console.error('[Faktura XL] Brak tagu <pdf> z danymi Base64 w zwrocie:', responseText);
      return null;
    }

    return Buffer.from(base64Data, 'base64');
  } catch (err) {
    console.error('[Faktura XL] downloadInvoicePdf Exception:', err);
    return null;
  }
}
