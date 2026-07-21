import { ChangeEvent, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, ApiError } from "../api/client";
import type { TargetCompanyImportResult } from "../api/types";
import { useToast } from "../context/ToastContext";
import { guessIndustryColumn, guessNameColumn, parseCsvPreview } from "../utils/csv";

const NO_INDUSTRY_COLUMN = "";

interface TargetCompanyCsvImportProps {
  onImported: () => void;
}

export default function TargetCompanyCsvImport({ onImported }: TargetCompanyCsvImportProps) {
  const { t } = useTranslation("settings");
  const { showToast } = useToast();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [headers, setHeaders] = useState<string[]>([]);
  const [previewRows, setPreviewRows] = useState<string[][]>([]);
  const [nameColumn, setNameColumn] = useState("");
  const [industryColumn, setIndustryColumn] = useState(NO_INDUSTRY_COLUMN);
  const [isImporting, setIsImporting] = useState(false);
  const [result, setResult] = useState<TargetCompanyImportResult | null>(null);

  function reset() {
    setFile(null);
    setHeaders([]);
    setPreviewRows([]);
    setNameColumn("");
    setIndustryColumn(NO_INDUSTRY_COLUMN);
    setResult(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  function openPanel() {
    setIsOpen(true);
  }

  function closePanel() {
    setIsOpen(false);
    reset();
  }

  async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const selected = event.target.files?.[0];
    if (!selected) return;
    setResult(null);
    setFile(selected);
    const text = await selected.text();
    const { headers: parsedHeaders, rows } = parseCsvPreview(text);
    setHeaders(parsedHeaders);
    setPreviewRows(rows);
    setNameColumn(guessNameColumn(parsedHeaders) ?? parsedHeaders[0] ?? "");
    setIndustryColumn(guessIndustryColumn(parsedHeaders) ?? NO_INDUSTRY_COLUMN);
  }

  async function handleImport() {
    if (!file || !nameColumn) return;
    setIsImporting(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("name_column", nameColumn);
      if (industryColumn) {
        formData.append("industry_column", industryColumn);
      }
      const imported = await api.postForm<TargetCompanyImportResult>("/target-companies/import", formData);
      setResult(imported);
      onImported();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("targets.import.importFailed"), "error");
    } finally {
      setIsImporting(false);
    }
  }

  if (!isOpen) {
    return (
      <button type="button" className="secondary" onClick={openPanel}>
        {t("targets.import.openButton")}
      </button>
    );
  }

  return (
    <div className="panel-card">
      <h3>{t("targets.import.title")}</h3>
      <p className="subtitle">{t("targets.import.subtitle")}</p>

      {!file && (
        <label>
          {t("targets.import.chooseFile")}
          <input ref={fileInputRef} type="file" accept=".csv" onChange={handleFileChange} />
        </label>
      )}

      {file && !result && (
        <>
          <p className="field-hint">{t("targets.import.previewHint", { filename: file.name })}</p>
          <div className="field-row">
            <label>
              {t("targets.import.nameColumn")}
              <select value={nameColumn} onChange={(e) => setNameColumn(e.target.value)}>
                {headers.map((header) => (
                  <option key={header} value={header}>
                    {header}
                  </option>
                ))}
              </select>
            </label>
            <label>
              {t("targets.import.industryColumn")}
              <select value={industryColumn} onChange={(e) => setIndustryColumn(e.target.value)}>
                <option value={NO_INDUSTRY_COLUMN}>{t("targets.import.noIndustryColumn")}</option>
                {headers.map((header) => (
                  <option key={header} value={header}>
                    {header}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {previewRows.length > 0 && (
            <div className="table-scroll">
              <table className="news-usage-table">
                <thead>
                  <tr>
                    {headers.map((header) => (
                      <th key={header}>{header}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {previewRows.map((row, idx) => (
                    <tr key={idx}>
                      {row.map((cell, cellIdx) => (
                        <td key={cellIdx}>{cell}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="actions">
            <button type="button" disabled={!nameColumn || isImporting} onClick={handleImport}>
              {isImporting ? t("targets.import.importing") : t("targets.import.importButton")}
            </button>
            <button type="button" onClick={closePanel} disabled={isImporting}>
              {t("targets.cancel")}
            </button>
          </div>
        </>
      )}

      {result && (
        <>
          <p className="field-hint">
            {t("targets.import.resultSummary", {
              created: result.created.length,
              skipped: result.skipped.length,
              errors: result.errors.length,
            })}
          </p>
          {result.skipped.length > 0 && (
            <ul className="field-hint">
              {result.skipped.map((row) => (
                <li key={row.row}>
                  {t("targets.import.skippedRow", { row: row.row, name: row.name, reason: row.reason })}
                </li>
              ))}
            </ul>
          )}
          {result.errors.length > 0 && (
            <ul className="field-hint error-text">
              {result.errors.map((row) => (
                <li key={row.row}>{t("targets.import.errorRow", { row: row.row, reason: row.reason })}</li>
              ))}
            </ul>
          )}
        </>
      )}

      {(!file || result) && (
        <div className="actions">
          <button type="button" onClick={closePanel}>
            {result ? t("targets.import.done") : t("targets.cancel")}
          </button>
        </div>
      )}
    </div>
  );
}
