// Minimal client-side CSV parsing for the import column-mapping preview only (header
// row + a few sample rows) — the backend does the authoritative parse of the full file
// with Python's csv module, so this doesn't need to handle every real-world edge case.

export function parseCsvLine(line: string): string[] {
  const result: string[] = [];
  let current = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const char = line[i];
    if (inQuotes) {
      if (char === '"') {
        if (line[i + 1] === '"') {
          current += '"';
          i++;
        } else {
          inQuotes = false;
        }
      } else {
        current += char;
      }
    } else if (char === '"') {
      inQuotes = true;
    } else if (char === ",") {
      result.push(current);
      current = "";
    } else {
      current += char;
    }
  }
  result.push(current);
  return result;
}

export interface CsvPreview {
  headers: string[];
  rows: string[][];
}

export function parseCsvPreview(text: string, maxRows = 5): CsvPreview {
  const lines = text.split(/\r\n|\n|\r/).filter((line) => line.length > 0);
  const headers = lines.length > 0 ? parseCsvLine(lines[0]) : [];
  const rows = lines.slice(1, 1 + maxRows).map(parseCsvLine);
  return { headers, rows };
}

const NAME_HEADER_CANDIDATES = ["account name", "company name", "company", "name"];
const INDUSTRY_HEADER_CANDIDATES = ["industry"];

function guessColumn(headers: string[], candidates: string[]): string | null {
  for (const candidate of candidates) {
    const match = headers.find((h) => h.trim().toLowerCase() === candidate);
    if (match) return match;
  }
  return null;
}

export function guessNameColumn(headers: string[]): string | null {
  return guessColumn(headers, NAME_HEADER_CANDIDATES);
}

export function guessIndustryColumn(headers: string[]): string | null {
  return guessColumn(headers, INDUSTRY_HEADER_CANDIDATES);
}
