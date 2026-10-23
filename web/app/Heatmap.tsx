"use client";
import { useAuthActions } from "@convex-dev/auth/react";
import { useConvex, useQuery } from "convex/react";
import { useEffect, useRef } from "react";
import { api } from "../convex/_generated/api";
import { MARKUP, SCRIPT } from "../generated/page";
import { installHost } from "./host";

// Runs the same page the daily run builds (site/template.html), with the
// report and comments coming from Convex.
export default function Heatmap() {
  const client = useConvex();
  const { signOut } = useAuthActions();
  const me = useQuery(api.people.me);
  const report = useQuery(api.report.latest);
  const ref = useRef<HTMLDivElement>(null);
  const shown = useRef<string | null>(null);

  useEffect(() => {
    if (!report || shown.current || !ref.current) return;
    shown.current = report.runId;
    installHost(client, () => void signOut().then(() => window.location.reload()));
    const el = ref.current;
    el.innerHTML = MARKUP;
    const data = document.createElement("script");
    data.type = "application/json";
    data.id = "heatmap-data";
    data.textContent = report.json;
    el.append(data);
    const page = document.createElement("script");
    page.textContent = SCRIPT;
    el.append(page);
  }, [report, client, signOut]);

  if (me === null)
    return (
      <Message>
        This login isn&apos;t on the invite list. <button onClick={() => void signOut()}>Sign out</button>
      </Message>
    );
  if (report === null) return <Message>No report has been published here yet.</Message>;
  return (
    <>
      {report && shown.current && report.runId !== shown.current && (
        <div className="hm-banner" role="status">
          A newer report is ready. <button onClick={() => window.location.reload()}>Show it</button>
        </div>
      )}
      {report === undefined && <p className="hm-wait">Loading the latest report…</p>}
      <div ref={ref} />
    </>
  );
}

function Message({ children }: { children: React.ReactNode }) {
  return <p className="hm-wait">{children}</p>;
}
