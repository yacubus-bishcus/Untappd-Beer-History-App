"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { Icon } from "@/components/icons";
import type { ImportResult } from "@/lib/types";

export function ImportPanel({
  onClose,
}: {
  onClose: () => void;
}) {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [status, setStatus] = useState<"idle" | "uploading" | "success" | "error">(
    "idle",
  );
  const [message, setMessage] = useState("");

  function chooseFile(nextFile?: File) {
    if (!nextFile) return;
    if (!nextFile.name.toLowerCase().endsWith(".csv")) {
      setStatus("error");
      setMessage("Choose the my_beers.csv file created by the desktop app.");
      return;
    }
    setFile(nextFile);
    setStatus("idle");
    setMessage("");
  }

  async function submit() {
    if (!file) {
      setStatus("error");
      setMessage("Choose a CSV file first.");
      return;
    }

    setStatus("uploading");
    setMessage("");
    const body = new FormData();
    body.set("file", file);

    try {
      const response = await fetch("/api/import", { method: "POST", body });
      const payload = (await response.json()) as ImportResult & { error?: string };

      if (!response.ok) {
        throw new Error(payload.error ?? "The import could not be completed.");
      }

      setStatus("success");
      setMessage(
        `${payload.synced.toLocaleString()} rows synced. Your archive now has ${payload.libraryTotal.toLocaleString()} check-ins.`,
      );
      router.refresh();
    } catch (error) {
      setStatus("error");
      setMessage(error instanceof Error ? error.message : "The import could not be completed.");
    }
  }

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        aria-labelledby="import-title"
        aria-modal="true"
        className="import-modal"
        onMouseDown={(event) => event.stopPropagation()}
        role="dialog"
      >
        <button className="modal-close" onClick={onClose} type="button" aria-label="Close import">
          ×
        </button>
        <span className="modal-icon"><Icon name="upload" size={24} /></span>
        <div className="modal-heading">
          <span className="eyebrow">Update your archive</span>
          <h2 id="import-title">Import beer history</h2>
          <p>
            Upload <strong>data/my_beers.csv</strong> from the desktop app. Existing
            check-ins are updated, so importing the same file twice is safe.
          </p>
        </div>

        <div
          className={`drop-zone ${dragging ? "dragging" : ""} ${file ? "has-file" : ""}`}
          onClick={() => inputRef.current?.click()}
          onDragEnter={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDragOver={(event) => event.preventDefault()}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            chooseFile(event.dataTransfer.files[0]);
          }}
          role="button"
          tabIndex={0}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") inputRef.current?.click();
          }}
        >
          <input
            accept=".csv,text/csv"
            hidden
            onChange={(event) => chooseFile(event.target.files?.[0])}
            ref={inputRef}
            type="file"
          />
          <Icon name={file ? "archive" : "upload"} size={28} />
          {file ? (
            <>
              <strong>{file.name}</strong>
              <span>{(file.size / 1024).toFixed(1)} KB · Ready to sync</span>
            </>
          ) : (
            <>
              <strong>Drop your CSV here</strong>
              <span>or click to choose a file · 5 MB maximum</span>
            </>
          )}
        </div>

        {message && <p className={`import-message ${status}`} role="status">{message}</p>}

        <div className="modal-actions">
          <button className="secondary-button" onClick={onClose} type="button">Cancel</button>
          <button
            className="primary-button"
            disabled={!file || status === "uploading"}
            onClick={submit}
            type="button"
          >
            {status === "uploading" ? "Syncing…" : status === "success" ? "Sync again" : "Sync history"}
          </button>
        </div>
      </section>
    </div>
  );
}
