import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { PATIENT_ID } from "./config";

type Doc = {
  id: number; filename: string; status: "processing" | "ready" | "failed"; error: string | null;
  type: string | null; date: string | null; author: string | null; uploaded_by: string; uploaded_at: string;
  pending: number; approved: number; rejected: number;
};
type Fact = {
  id: number; kind: string; summary: string; page: number; quote: string; verified: boolean; companion_can_say: boolean;
  status: "pending" | "approved" | "rejected"; reviewed_by: string | null; conflict: string | null;
};
type Detail = {
  id: number; filename: string; status: string; error: string | null; type: string | null; date: string | null; author: string | null;
  named_patient: string | null; name_mismatch: boolean; patient: string; facts: Fact[];
};

// ?patient=99 points the page at the test patient, same as the family portal
const PID = Number(new URLSearchParams(window.location.search).get("patient")) || PATIENT_ID;
const MAX_BYTES = 3 * 1024 * 1024;

const KIND: Record<string, string> = {
  medication: "Medicine", appointment: "Appointment", instruction: "Instruction", test_result: "Test result",
  diagnosis_stated: "Diagnosis stated", contact: "Contact", other: "Other",
};
const TYPE: Record<string, string> = {
  clinic_letter: "Clinic letter", prescription: "Prescription", lab_result: "Test result", discharge_summary: "Discharge summary",
  appointment: "Appointment letter", other: "Document",
};
const button = "min-h-11 rounded-lg px-4 text-base font-semibold disabled:opacity-40";
const day = (iso: string) => new Date(iso).toLocaleDateString([], { dateStyle: "medium" });

const toBase64 = (f: File) =>
  new Promise<string>((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result).split(",")[1] ?? "");
    r.onerror = () => reject(r.error);
    r.readAsDataURL(f);
  });

export default function Documents() {
  const [role, setRole] = useState<"owner" | "member" | null>(null);
  const [docs, setDocs] = useState<Doc[] | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  const loadList = useCallback(async () => {
    try {
      const r = await api(`/family/${PID}/documents`);
      if (!r.ok) throw new Error(String(r.status));
      setDocs((await r.json()).documents);
    } catch {
      setNote("Cannot reach the server.");
    }
  }, []);

  const loadDetail = useCallback(async (id: number) => {
    const r = await api(`/family/${PID}/documents/${id}`);
    if (r.ok) setDetail(await r.json());
  }, []);

  useEffect(() => {
    (async () => {
      // the deployed site says who is signed in; a local dev screen has no such route and is the owner
      const who = await api("/whoami");
      const r = who.ok ? (await who.json()).role : "owner";
      setRole(r);
      if (r === "owner") loadList();
    })().catch(() => setNote("Cannot reach the server."));
  }, [loadList]);

  // while a document is being read, check again every few seconds
  const reading = docs?.some((d) => d.status === "processing") ?? false;
  useEffect(() => {
    if (!reading) return;
    const t = setInterval(() => {
      loadList();
      if (open) loadDetail(open);
    }, 3000);
    return () => clearInterval(t);
  }, [reading, open, loadList, loadDetail]);

  useEffect(() => {
    if (open) loadDetail(open);
    else setDetail(null);
  }, [open, loadDetail]);

  const upload = async (file: File | undefined) => {
    if (!file) return;
    setNote("");
    if (file.size > MAX_BYTES) return setNote("That file is larger than 3 MB.");
    setBusy(true);
    try {
      const r = await api(`/family/${PID}/documents`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ filename: file.name, content_b64: await toBase64(file) }),
      });
      const out = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(out.detail ?? String(r.status));
      setNote(out.existing ? "That document was already uploaded." : "Uploaded. Reading it now, this takes a few seconds.");
      await loadList();
      setOpen(out.id);
    } catch (e) {
      setNote(e instanceof Error && e.message ? e.message : "Could not upload.");
    } finally {
      setBusy(false);
    }
  };

  const review = async (fid: number, action: "approve" | "reject") => {
    if (!open) return;
    setBusy(true);
    try {
      const r = await api(`/family/${PID}/documents/${open}/facts/${fid}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ action }),
      });
      if (!r.ok) throw new Error(String(r.status));
      await Promise.all([loadDetail(open), loadList()]);
    } catch {
      setNote("That did not work. Try again.");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: number) => {
    if (!window.confirm("Delete this document and everything the companion learned from it?")) return;
    setBusy(true);
    try {
      const r = await api(`/family/${PID}/documents/${id}/delete`, { method: "POST", headers: { "content-type": "application/json" }, body: "{}" });
      if (!r.ok) throw new Error(String(r.status));
      setOpen(null);
      await loadList();
    } catch {
      setNote("Could not delete.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-dvh bg-neutral-100 text-neutral-900">
      <div className="mx-auto max-w-3xl px-4 py-5 pb-12">
        <header className="flex items-baseline justify-between gap-3">
          <h1 className="text-xl font-bold">Medical documents</h1>
          <a href="/caregiver" className="text-base font-medium text-neutral-600 underline underline-offset-4">Back to portal</a>
        </header>

        {role === "member" && (
          <p className="mt-4 rounded-2xl border border-neutral-300 bg-white p-4 text-base">Only the owner can upload and review medical documents.</p>
        )}

        {role === "owner" && (
          <div className="mt-4 space-y-4">
            <section className="rounded-2xl border border-neutral-300 bg-white p-4 text-base text-neutral-700">
              <p>
                Upload a clinic letter or a prescription as a PDF. The system lists what it says, with the exact words and the page.{" "}
                <b className="text-neutral-900">Nothing is used until you approve it.</b>
              </p>
              <p className="mt-2">
                The companion only repeats medicines, appointments and instructions, and always says where they come from. It never gives
                advice about them. A diagnosis or a test score can be kept as a family record, and the companion will not say it.
              </p>
              <label className="mt-3 flex min-h-11 cursor-pointer items-center justify-center rounded-lg bg-neutral-900 px-5 text-base font-semibold text-white">
                {busy ? "Working..." : "Upload a PDF"}
                <input
                  type="file"
                  accept="application/pdf"
                  className="sr-only"
                  disabled={busy}
                  onChange={(e) => {
                    upload(e.target.files?.[0]);
                    e.target.value = "";
                  }}
                />
              </label>
              <p role="status" className="mt-2 min-h-6 font-medium text-neutral-900">{note}</p>
            </section>

            <section className="rounded-2xl border border-neutral-300 bg-white p-4">
              <h2 className="text-lg font-bold">Documents</h2>
              <ul className="mt-2 space-y-2">
                {docs && docs.length === 0 && <li className="text-base text-neutral-600">Nothing uploaded yet.</li>}
                {docs?.map((d) => (
                  <li key={d.id} className={`rounded-lg border p-3 ${open === d.id ? "border-neutral-900" : "border-neutral-200"}`}>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="min-w-0">
                        <p className="truncate text-base font-semibold">{d.filename}</p>
                        <p className="text-sm text-neutral-600">
                          {[d.type ? TYPE[d.type] : null, d.author, d.date ? day(d.date) : null].filter(Boolean).join(", ") || "Reading..."}
                        </p>
                        <p className="text-sm font-medium">
                          {d.status === "processing" && "Reading the document..."}
                          {d.status === "failed" && `Could not read it. ${d.error ?? ""}`}
                          {d.status === "ready" && `${d.pending} to review, ${d.approved} approved, ${d.rejected} rejected`}
                        </p>
                      </div>
                      <div className="flex gap-2">
                        <button onClick={() => setOpen(open === d.id ? null : d.id)} className={`${button} border border-neutral-900`}>
                          {open === d.id ? "Close" : "Review"}
                        </button>
                        <button onClick={() => remove(d.id)} disabled={busy} className={`${button} border border-neutral-400`}>Delete</button>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            </section>

            {detail && open === detail.id && (
              <section className="rounded-2xl border border-neutral-300 bg-white p-4">
                <h2 className="text-lg font-bold">Review: {detail.filename}</h2>
                {detail.name_mismatch && (
                  <p className="mt-2 rounded-lg bg-yellow-100 px-3 py-2 text-base font-medium">
                    This document names &ldquo;{detail.named_patient}&rdquo;, but this profile is {detail.patient}. Check that it is the right
                    person before approving anything.
                  </p>
                )}
                {detail.status === "processing" && <p className="mt-2 text-base">Reading the document...</p>}
                <ul className="mt-3 space-y-3">
                  {detail.facts.map((f) => (
                    <li key={f.id} className={`rounded-xl border p-3 ${f.status === "approved" ? "border-green-600 bg-green-50" : f.status === "rejected" ? "border-neutral-200 bg-neutral-50 text-neutral-500" : "border-neutral-300"}`}>
                      <div className="flex flex-wrap items-center gap-2 text-sm font-bold">
                        <span className="rounded-full bg-neutral-900 px-2 py-0.5 text-white">{KIND[f.kind] ?? f.kind}</span>
                        <span className="text-neutral-600">Page {f.page}</span>
                        {!f.companion_can_say && <span className="rounded-full bg-neutral-200 px-2 py-0.5 text-neutral-800">Family record only</span>}
                      </div>
                      <p className="mt-2 text-lg font-semibold leading-snug">{f.summary}</p>
                      <blockquote className="mt-2 border-l-4 border-neutral-300 pl-3 text-base italic text-neutral-700 break-words">
                        &ldquo;{f.quote}&rdquo;
                      </blockquote>
                      {!f.verified && (
                        <p className="mt-2 rounded-lg bg-red-100 px-3 py-2 text-base font-medium text-neutral-900">
                          These exact words were not found on the page, so this cannot be approved.
                        </p>
                      )}
                      {f.conflict && <p className="mt-2 rounded-lg bg-yellow-100 px-3 py-2 text-base font-medium">{f.conflict}</p>}
                      {!f.companion_can_say && f.status === "pending" && (
                        <p className="mt-2 text-sm text-neutral-600">If approved, this is kept for the family. The companion will not say it.</p>
                      )}
                      <div className="mt-3 flex flex-wrap items-center gap-2">
                        {f.status !== "approved" && (
                          <button onClick={() => review(f.id, "approve")} disabled={busy || !f.verified} className={`${button} bg-green-700 text-white`}>Approve</button>
                        )}
                        {f.status !== "rejected" && (
                          <button onClick={() => review(f.id, "reject")} disabled={busy} className={`${button} border border-neutral-400`}>
                            {f.status === "approved" ? "Withdraw" : "Reject"}
                          </button>
                        )}
                        {f.status === "approved" && (
                          <span className="text-sm font-semibold text-green-800">
                            Approved by {f.reviewed_by}{f.companion_can_say ? ". The companion can say this." : ". Family record only."}
                          </span>
                        )}
                        {f.status === "rejected" && <span className="text-sm font-semibold">Rejected</span>}
                      </div>
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
