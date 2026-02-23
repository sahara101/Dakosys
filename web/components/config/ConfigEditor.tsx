"use client";

import dynamic from "next/dynamic";

const MonacoEditor = dynamic(
  () => import("@monaco-editor/react").then((mod) => mod.default),
  { ssr: false, loading: () => <div className="h-full bg-zinc-950 animate-pulse rounded-lg" /> }
);

interface ConfigEditorProps {
  value: string;
  onChange: (val: string) => void;
  height?: string;
}

export function ConfigEditor({ value, onChange, height = "60vh" }: ConfigEditorProps) {
  return (
    <div className="rounded-lg overflow-hidden border border-zinc-700" style={{ height }}>
      <MonacoEditor
        height="100%"
        defaultLanguage="yaml"
        theme="vs-dark"
        value={value}
        onChange={(v) => onChange(v ?? "")}
        options={{
          minimap: { enabled: false },
          fontSize: 13,
          lineNumbers: "on",
          scrollBeyondLastLine: false,
          wordWrap: "on",
          tabSize: 2,
          automaticLayout: true,
        }}
      />
    </div>
  );
}
