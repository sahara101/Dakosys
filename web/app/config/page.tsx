"use client";

import { useEffect, useRef, useState } from "react";
import { Button, Spinner, Tooltip } from "@nextui-org/react";
import { api } from "@/lib/api";
import { ConfigEditor } from "@/components/config/ConfigEditor";
import { SaveWarningModal } from "@/components/config/SaveWarningModal";
import { ConfigReferenceModal } from "@/components/config/ConfigReferenceModal";

export default function ConfigPage() {
  const [config, setConfig] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [showRef, setShowRef] = useState(false);
  const [dirty, setDirty] = useState(false);
  const importRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.getConfig().then((res) => {
      setConfig(res.config);
      setError(res.error ?? null);
    }).catch((e: unknown) => {
      setError(e instanceof Error ? e.message : "Failed to load config");
    }).finally(() => setLoading(false));
  }, []);

  const handleImport = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      const text = ev.target?.result;
      if (typeof text === "string") {
        setConfig(text);
        setDirty(true);
        setSuccess(false);
      }
    };
    reader.readAsText(file);
    e.target.value = "";
  };

  const handleChange = (val: string) => {
    setConfig(val);
    setDirty(true);
    setSuccess(false);
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setSuccess(false);
    try {
      await api.updateConfig(config);
      setSuccess(true);
      setDirty(false);
      setTimeout(() => setSuccess(false), 4000);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to save config");
    } finally {
      setSaving(false);
      setShowModal(false);
    }
  };

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-6 gap-3">
        <div>
          <h1 className="text-3xl font-bold text-white">Configuration</h1>
          <p className="text-zinc-400 mt-1">
            Edit <code className="text-violet-300 text-sm">config.yaml</code> — secrets are masked
          </p>
        </div>
        <div className="flex items-center flex-wrap gap-2">
          {success && <span className="text-green-400 text-sm mr-1">Saved!</span>}
          {dirty && !saving && <span className="text-yellow-400 text-xs mr-1">Unsaved changes</span>}

          <input ref={importRef} type="file" accept=".yaml,.yml,text/yaml,text/x-yaml,application/x-yaml" className="hidden" onChange={handleImport} />
          <Tooltip
            content="Browse all available config.yaml options with types and defaults"
            placement="bottom"
            className="dark max-w-xs"
          >
            <Button size="sm" variant="flat" color="secondary" onPress={() => setShowRef(true)}>
              Reference
            </Button>
          </Tooltip>
          <Tooltip
            content="Load a config.yaml file from your computer into the editor"
            placement="bottom"
            className="dark max-w-xs"
          >
            <Button size="sm" variant="bordered" color="default" onPress={() => importRef.current?.click()}>
              Import
            </Button>
          </Tooltip>
          <Tooltip
            content="Download the active config.yaml to your computer (includes real secrets)"
            placement="bottom"
            className="dark max-w-xs"
          >
            <a href="/api/config/export" download="config.yaml">
              <Button size="sm" variant="bordered" color="default">
                Export
              </Button>
            </a>
          </Tooltip>

          <div className="w-px h-5 bg-zinc-700 mx-1" />

          <Button
            color="secondary"
            isDisabled={!dirty || saving}
            isLoading={saving}
            onPress={() => setShowModal(true)}
          >
            Save Config
          </Button>
        </div>
      </div>

      {error && (
        <div className="bg-red-950/50 border border-red-800 rounded-lg p-4 mb-4">
          <p className="text-red-400 text-sm">{error}</p>
        </div>
      )}

      {loading ? (
        <div className="flex justify-center h-40 items-center">
          <Spinner color="secondary" />
        </div>
      ) : (
        <ConfigEditor value={config} onChange={handleChange} />
      )}

      <SaveWarningModal
        isOpen={showModal}
        onConfirm={handleSave}
        onCancel={() => setShowModal(false)}
      />
      <ConfigReferenceModal
        isOpen={showRef}
        onClose={() => setShowRef(false)}
      />
    </div>
  );
}
