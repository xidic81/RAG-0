"use client";

import { useEffect, useState } from "react";
import { health, type Health as HealthStatus } from "@/lib/api";

const services = ["postgres", "pinecone"] as const;

type HealthState = HealthStatus | { error: string } | null;

export default function Health() {
  const [status, setStatus] = useState<HealthState>(null);

  useEffect(() => {
    health().then(setStatus).catch((error: unknown) => {
      const message = error instanceof Error ? error.message : String(error);
      setStatus({ error: `error: ${message}` });
    });
  }, []);

  const llmProvider = status && !("error" in status) ? status.llm_provider : "llm";
  const llmStatus = status && !("error" in status) ? status.llm : undefined;
  const llmTitle = status && "error" in status ? status.error : llmStatus ?? "checking";

  return (
    <div className="flex items-center gap-4 text-sm" aria-label="Service health">
      {services.map((service) => {
        const serviceStatus = status && !("error" in status) ? status[service] : undefined;
        const isHealthy = serviceStatus === "ok";
        const title = status && "error" in status ? status.error : serviceStatus ?? "checking";

        return (
          <span key={service} title={title} className="whitespace-nowrap">
            {service} <span className={isHealthy ? "text-green-600" : "text-red-600"}>●</span>
          </span>
        );
      })}
      <span title={llmTitle} className="whitespace-nowrap">
        {llmProvider} <span className={llmStatus === "ok" ? "text-green-600" : "text-red-600"}>●</span>
      </span>
    </div>
  );
}
