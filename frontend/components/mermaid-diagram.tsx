"use client";

import { useEffect, useId, useState } from "react";

export function MermaidDiagram({ definition }: { definition: string }) {
  const reactId = useId();
  const [svg, setSvg] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const id = `mermaid-${reactId.replace(/[^a-zA-Z0-9]/g, "")}`;

    async function render() {
      try {
        const { default: mermaid } = await import("mermaid");
        if (cancelled) return;
        mermaid.initialize({
          startOnLoad: false,
          securityLevel: "strict",
          theme: "base",
          themeVariables: {
            primaryColor: "#eff4ff",
            primaryTextColor: "#263752",
            primaryBorderColor: "#96b1ee",
            lineColor: "#8598b4",
            fontFamily: "ui-sans-serif, system-ui, sans-serif",
          },
        });
        const result = await mermaid.render(id, definition);
        if (!cancelled) {
          setSvg(result.svg);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "Could not render diagram",
          );
          setSvg("");
        }
      }
    }

    void render();
    return () => {
      cancelled = true;
    };
  }, [definition, reactId]);

  if (error) {
    return (
      <div className="errorBox">
        <p>
          The diagram could not be displayed. The architecture details are
          available below.
        </p>
        <details>
          <summary>Diagram source</summary>
          <pre>{definition}</pre>
        </details>
      </div>
    );
  }

  return (
    <div
      className="diagram"
      role="img"
      aria-label="Generated system architecture diagram"
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}
