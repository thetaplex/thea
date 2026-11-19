import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  Eye,
  EyeOff,
  Plus,
  Server,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import type React from "react";
import { useEffect, useRef, useState } from "react";
import {
  type AppSettings,
  api,
  getProviderMeta,
  type McpRemoteTool,
  type McpServerConfig,
  PROVIDERS,
  type ProviderConfig,
  type SkillInfo,
} from "../lib/ipc";
import { hasUnsavedKey } from "../lib/providerKeys";
import { customSkills } from "../lib/skills";
import { useAppStore } from "../stores/useAppStore";

export type SettingsTab = "providers" | "skills" | "mcp";

export const SettingsModal: React.FC<{
  onClose: () => void;
  initialTab?: SettingsTab;
}> = ({ onClose, initialTab = "providers" }) => {
  const {
    settings,
    providers,
    refreshProviders,
    models,
    skills: allSkills,
    toggleSkill,
    refreshSkills,
    activeProjectId,
    mcpServers,
    refreshMcpServers,
    refreshModels,
  } = useAppStore();
  const skills = customSkills(allSkills);
  const [form, setForm] = useState<AppSettings | null>(settings);
  const [testedModels, setTestedModels] = useState<string[]>([]);
  const [tab, setTab] = useState<SettingsTab>(initialTab);
  const [testStatus, setTestStatus] = useState<string | null>(null);
  const [testError, setTestError] = useState<string | null>(null);
  const [showApiKey, setShowApiKey] = useState(false);
  const [unsavedKeyWarning, setUnsavedKeyWarning] = useState(false);

  // Add New Provider inline form state
  const [showAddProvider, setShowAddProvider] = useState(false);
  const [newProvName, setNewProvName] = useState("");
  const [newProvProtocol, setNewProvProtocol] = useState<"openai" | "ollama">("openai");
  const [newProvUrl, setNewProvUrl] = useState("http://127.0.0.1:8080/v1");

  // Model Combo Box state
  const [comboOpen, setComboOpen] = useState(false);
  const [filterByTyping, setFilterByTyping] = useState(false);
  const comboRef = useRef<HTMLDivElement>(null);

  // Skills tab state
  const [selectedSkill, setSelectedSkill] = useState<SkillInfo | null>(null);
  const [showCreateSkill, setShowCreateSkill] = useState(false);
  const [skillName, setSkillName] = useState("");
  const [skillDesc, setSkillDesc] = useState("");
  const [skillScope, setSkillScope] = useState<"global" | "project">("global");
  const [skillBody, setSkillBody] = useState(
    "# Skill Instructions\n\n1. Explain when and how Thea should apply this workflow.\n",
  );
  const [skillError, setSkillError] = useState<string | null>(null);

  // New MCP server form
  const [showCreateMcp, setShowCreateMcp] = useState(false);
  const [mcpName, setMcpName] = useState("");
  const [mcpAutoApprove, setMcpAutoApprove] = useState(false);
  const [npxMissing, setNpxMissing] = useState(false);
  const [mcpCommand, setMcpCommand] = useState("npx");
  const [mcpArgs, setMcpArgs] = useState("-y @modelcontextprotocol/server-filesystem /tmp");
  const [mcpToolsPreview, setMcpToolsPreview] = useState<Record<string, McpRemoteTool[]>>({});

  const needsNpx = mcpServers.some((s) => s.enabled && s.command === "npx");
  useEffect(() => {
    if (!needsNpx) {
      setNpxMissing(false);
      return;
    }
    let stale = false;
    api
      .isCommandAvailable("npx")
      .then((ok) => {
        if (!stale) setNpxMissing(!ok);
      })
      .catch(() => {});
    return () => {
      stale = true;
    };
  }, [needsNpx]);

  useEffect(() => {
    if (settings) setForm(settings);
  }, [settings]);

  // Fill the model dropdown for whichever provider is picked, refetching as its URL or key is typed.
  const provId = form?.default_provider ?? "";
  const provEntry = providers.find((p) => p.id === provId);
  const provBaseUrl =
    form?.provider_configs?.[provId]?.base_url ||
    provEntry?.base_url ||
    getProviderMeta(provId).defaultBaseUrl;
  const provApiKey = form?.provider_configs?.[provId]?.api_key ?? provEntry?.api_key ?? "";
  useEffect(() => {
    setTestedModels([]);
    if (!provId) return;
    let stale = false;
    const timer = setTimeout(() => {
      api
        .listModelsForProvider(provId, provBaseUrl, provApiKey)
        .then((list) => {
          if (!stale) setTestedModels(list.map((m) => m.id));
        })
        .catch(() => {}); // unreachable provider: the Test button reports why
    }, 400);
    return () => {
      stale = true;
      clearTimeout(timer);
    };
  }, [provId, provBaseUrl, provApiKey]);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (comboRef.current && !comboRef.current.contains(e.target as Node)) {
        setComboOpen(false);
        setFilterByTyping(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  if (!form) return null;

  const activeProviderEntry = providers.find((p) => p.id === form.default_provider);
  const activeProviderMeta = getProviderMeta(form.default_provider);
  const activeProviderLabel = activeProviderEntry?.name || activeProviderMeta.label;
  const activeSuggestedModels =
    activeProviderEntry?.models && activeProviderEntry.models.length > 0
      ? activeProviderEntry.models
      : activeProviderMeta.suggestedModels;

  const getProviderConfig = (provId: string): ProviderConfig => {
    const entry = providers.find((p) => p.id === provId);
    const meta = getProviderMeta(provId);
    const defaultUrl = entry?.base_url || meta.defaultBaseUrl;
    const existing = form.provider_configs?.[provId];
    if (existing) {
      return {
        base_url: existing.base_url || defaultUrl,
        api_key: existing.api_key ?? entry?.api_key ?? "",
      };
    }
    if (entry) {
      return {
        base_url: entry.base_url || defaultUrl,
        api_key: entry.api_key || "",
      };
    }
    if (provId === "ollama") {
      return {
        base_url: form.ollama_base_url || defaultUrl,
        api_key: "",
      };
    }
    if (provId === "custom") {
      return {
        base_url: form.openai_base_url || defaultUrl,
        api_key: form.openai_api_key || "",
      };
    }
    return {
      base_url: defaultUrl,
      api_key: provId === "openai" ? form.openai_api_key || "" : "",
    };
  };

  const currentProvConfig = getProviderConfig(form.default_provider);

  const updateProviderConfig = (provId: string, patch: Partial<ProviderConfig>) => {
    const current = getProviderConfig(provId);
    const nextCfg: ProviderConfig = { ...current, ...patch };
    const nextMap = {
      ...(form.provider_configs || {}),
      [provId]: nextCfg,
    };
    const nextForm: AppSettings = {
      ...form,
      provider_configs: nextMap,
    };
    if (provId === "ollama" && patch.base_url !== undefined) {
      nextForm.ollama_base_url = patch.base_url;
    } else if (provId === "custom") {
      if (patch.base_url !== undefined) nextForm.openai_base_url = patch.base_url;
      if (patch.api_key !== undefined) nextForm.openai_api_key = patch.api_key;
    }
    setForm(nextForm);
  };

  // Closing drops the form, so a typed key that was only tested would be lost.
  const requestClose = () => {
    if (form && hasUnsavedKey(form, settings)) {
      setTab("providers");
      setShowAddProvider(false);
      setUnsavedKeyWarning(true);
    } else {
      onClose();
    }
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    await api.saveSettings(form);
    await refreshProviders();
    useAppStore.setState({
      settings: form,
      sessionProvider: form.default_provider,
      sessionModel: form.default_model,
    });
    const id = form.default_provider;
    const isLmStudio = /lm ?studio/i.test(`${id} ${activeProviderEntry?.name ?? ""}`);
    if (isLmStudio) {
      const { base_url, api_key } = getProviderConfig(id);
      const answers = await api.listModelsForProvider(id, base_url, api_key).then(
        () => true,
        () => false,
      );
      if (!answers) {
        setTestError(null);
        setTestStatus("Starting the LM Studio server...");
        try {
          await api.startLmStudioServer(base_url);
          setTestStatus(null);
        } catch (err) {
          // Settings are saved; stay open so the reason is visible.
          setTestStatus(null);
          setTestError(String(err));
          return;
        }
      }
    }
    await refreshModels();
    onClose();
  };

  const handleCreateNewProvider = async () => {
    if (!newProvName.trim() || !newProvUrl.trim()) return;
    const id = newProvName
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "");
    await api.saveProvider({
      id,
      name: newProvName.trim(),
      protocol: newProvProtocol,
      base_url: newProvUrl.trim(),
      api_key: "",
      enabled: true,
      models: [],
      is_builtin: false,
    });
    await refreshProviders();
    updateProviderConfig(id, { base_url: newProvUrl.trim(), api_key: "" });
    setForm((prev) => (prev ? { ...prev, default_provider: id, default_model: "" } : prev));
    setNewProvName("");
    setShowAddProvider(false);
  };

  const handleDeleteCurrentProvider = async () => {
    if (!activeProviderEntry || activeProviderEntry.is_builtin) return;
    await api.deleteProvider(activeProviderEntry.id);
    await refreshProviders();
    setForm({ ...form, default_provider: "ollama", default_model: "" });
  };

  const handleTest = async () => {
    const provId = form.default_provider;
    const cfg = getProviderConfig(provId);
    setTestStatus(`Testing ${activeProviderLabel}...`);
    setTestError(null);
    try {
      const list = await api.testProviderConnection(provId, cfg.base_url, cfg.api_key);
      const ids = list.map((m) => m.id);
      setTestedModels(ids);
      setTestStatus(`Connected to ${activeProviderLabel}! Found ${list.length} model(s).`);
    } catch (err) {
      setTestStatus(null);
      setTestError(String(err));
    }
  };

  const allModelOptions = (() => {
    const storeModelIds = models
      .filter((m) => m.provider === form.default_provider)
      .map((m) => m.id);
    return Array.from(new Set([...testedModels, ...storeModelIds, ...activeSuggestedModels]));
  })();

  const filteredModelOptions = (() => {
    if (!filterByTyping || !form.default_model.trim()) {
      return allModelOptions;
    }
    const q = form.default_model.toLowerCase();
    const matches = allModelOptions.filter((id) => id.toLowerCase().includes(q));
    return matches.length > 0 ? matches : allModelOptions;
  })();

  const handleAddMcp = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!mcpName.trim() || !mcpCommand.trim()) return;
    const cfg: McpServerConfig = {
      id: "",
      name: mcpName.trim(),
      command: mcpCommand.trim(),
      args: mcpArgs
        .split(/\s+/)
        .map((s) => s.trim())
        .filter(Boolean),
      env: {},
      enabled: true,
      auto_approve: mcpAutoApprove,
    };
    await api.saveMcpServer(cfg);
    setMcpName("");
    setMcpAutoApprove(false);
    setShowCreateMcp(false);
    await refreshMcpServers();
  };

  const handleTestMcp = async (srv: McpServerConfig) => {
    setTestError(null);
    try {
      const tools = await api.testMcpServer(srv);
      setMcpToolsPreview((p) => ({ ...p, [srv.id]: tools }));
    } catch (err) {
      setTestError(String(err));
    }
  };

  const handleCreateSkill = async (e: React.FormEvent) => {
    e.preventDefault();
    setSkillError(null);
    if (!skillName.trim() || !skillDesc.trim()) {
      setSkillError("Name and description are required.");
      return;
    }
    try {
      const created = await api.createSkill(
        activeProjectId,
        skillScope,
        skillName.trim(),
        skillDesc.trim(),
        skillBody,
      );
      await refreshSkills();
      setSelectedSkill(created);
      setShowCreateSkill(false);
      setSkillName("");
      setSkillDesc("");
    } catch (err) {
      setSkillError(String(err));
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-[#4a3219]/45 backdrop-blur-xs flex items-center justify-center p-4">
      <div className="theta-card max-w-xl w-full p-6 shadow-2xl max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between pb-3">
          <div className="flex items-center gap-2 flex-wrap">
            <button
              type="button"
              onClick={() => setTab("providers")}
              className={tab === "providers" ? "theta-btn" : "theta-btn-secondary"}
            >
              Models
            </button>
            <button
              type="button"
              onClick={() => setTab("skills")}
              className={tab === "skills" ? "theta-btn" : "theta-btn-secondary"}
            >
              <Sparkles className="w-3.5 h-3.5" />
              Skills ({skills.length})
            </button>
            <button
              type="button"
              onClick={() => setTab("mcp")}
              className={tab === "mcp" ? "theta-btn" : "theta-btn-secondary"}
            >
              <Server className="w-3.5 h-3.5" />
              MCP ({mcpServers.length})
            </button>
          </div>
          <button type="button" onClick={requestClose} className="theta-btn-secondary !p-1.5">
            <X className="w-4 h-4" />
          </button>
        </div>

        {tab === "providers" && (
          <form onSubmit={handleSave} className="space-y-4 pt-2 text-xs overflow-y-auto">
            <div className="flex items-center justify-between gap-2">
              <p className="text-[#8c7358]">
                Configure local or cloud model providers, endpoints, and API keys.
              </p>
              <button
                type="button"
                onClick={() => setShowAddProvider((s) => !s)}
                className="theta-btn shrink-0"
              >
                <Plus className="w-3.5 h-3.5" />
                {showAddProvider ? "Back to Models" : "New Provider"}
              </button>
            </div>

            {showAddProvider ? (
              <div className="p-3.5 rounded-xl bg-[#f3ece0] space-y-2.5">
                <div className="font-semibold text-[#4a3219]">Add Model Provider</div>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label htmlFor="provider-name" className="block text-[#8c7358] mb-1">
                      Provider Name
                    </label>
                    <input
                      id="provider-name"
                      type="text"
                      value={newProvName}
                      onChange={(e) => setNewProvName(e.target.value)}
                      placeholder="e.g. Together AI"
                      className="w-full bg-white rounded-lg px-2.5 py-1.5 text-[#4a3219]"
                    />
                  </div>
                  <div>
                    <label htmlFor="api-protocol" className="block text-[#8c7358] mb-1">
                      API Protocol
                    </label>
                    <select
                      id="api-protocol"
                      value={newProvProtocol}
                      onChange={(e) => setNewProvProtocol(e.target.value as "openai" | "ollama")}
                      className="w-full bg-white rounded-lg px-2.5 py-1.5 text-[#4a3219]"
                    >
                      <option value="openai">OpenAI-Compatible API</option>
                      <option value="ollama">Ollama API</option>
                    </select>
                  </div>
                </div>
                <div>
                  <label htmlFor="base-url" className="block text-[#8c7358] mb-1">
                    Base URL
                  </label>
                  <input
                    id="base-url"
                    type="text"
                    value={newProvUrl}
                    onChange={(e) => setNewProvUrl(e.target.value)}
                    placeholder="https://api.together.xyz/v1"
                    className="w-full bg-white rounded-lg px-2.5 py-1.5 text-[#4a3219]"
                  />
                </div>
                <div className="flex justify-end gap-2 pt-1">
                  <button
                    type="button"
                    onClick={() => setShowAddProvider(false)}
                    className="theta-btn-secondary"
                  >
                    Cancel
                  </button>
                  <button type="button" onClick={handleCreateNewProvider} className="theta-btn">
                    Save Provider
                  </button>
                </div>
              </div>
            ) : (
              <>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <div className="block text-[#4a3219] font-medium">Provider</div>
                      {activeProviderEntry && !activeProviderEntry.is_builtin && (
                        <button
                          type="button"
                          onClick={handleDeleteCurrentProvider}
                          className="theta-btn-secondary !px-2 !py-0.5 text-[11px]"
                          title="Delete custom provider"
                        >
                          <Trash2 className="w-3 h-3" />
                          Remove
                        </button>
                      )}
                    </div>
                    <select
                      value={form.default_provider}
                      onChange={(e) => {
                        const nextProv = e.target.value;
                        setTestStatus(null);
                        setTestError(null);
                        setComboOpen(false);
                        setFilterByTyping(false);
                        setForm({
                          ...form,
                          default_provider: nextProv,
                          default_model: "",
                        });
                      }}
                      className="w-full bg-[#f3ece0] rounded-lg px-3 py-2 text-[#4a3219]"
                    >
                      {(providers.length > 0
                        ? providers.map((p) => ({ id: p.id, label: p.name }))
                        : PROVIDERS
                      ).map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.label}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="relative" ref={comboRef}>
                    <div className="block text-[#4a3219] font-medium mb-1">Model</div>
                    <div className="relative flex items-center">
                      <input
                        type="text"
                        value={form.default_model}
                        onFocus={() => {
                          setFilterByTyping(false);
                          setComboOpen(true);
                        }}
                        onChange={(e) => {
                          setForm({ ...form, default_model: e.target.value });
                          setFilterByTyping(true);
                          setComboOpen(true);
                        }}
                        placeholder="Select or type model ID..."
                        className="w-full bg-[#f3ece0] rounded-lg pl-3 pr-8 py-2 text-[#4a3219]"
                      />
                      <button
                        type="button"
                        onClick={() => {
                          setFilterByTyping(false);
                          setComboOpen((prev) => !prev);
                        }}
                        title="Show model list"
                        className="absolute right-1.5 p-1 text-[#70553a] hover:text-[#4a3219] rounded-md"
                      >
                        <ChevronDown className="w-3.5 h-3.5" />
                      </button>
                    </div>

                    {comboOpen && filteredModelOptions.length > 0 && (
                      <div className="absolute z-30 left-0 right-0 mt-1 max-h-48 overflow-y-auto rounded-lg bg-[#faf7f1] shadow-lg py-1">
                        {filteredModelOptions.map((id) => {
                          const isSelected = id === form.default_model;
                          return (
                            <button
                              key={id}
                              type="button"
                              onClick={() => {
                                setForm({ ...form, default_model: id });
                                setComboOpen(false);
                                setFilterByTyping(false);
                              }}
                              className={`w-full text-left px-3 py-1.5 text-xs truncate transition-colors ${
                                isSelected
                                  ? "bg-[#e3d7c3] text-[#4a3219] font-semibold"
                                  : "text-[#5c4024] hover:bg-[#efe7d8]"
                              }`}
                            >
                              {id}
                            </button>
                          );
                        })}
                      </div>
                    )}
                  </div>

                  <div>
                    <label htmlFor="searxng-url" className="block text-[#4a3219] font-medium mb-1">
                      SearXNG URL
                    </label>
                    <input
                      id="searxng-url"
                      type="text"
                      value={form.searxng_url}
                      onChange={(e) => setForm({ ...form, searxng_url: e.target.value })}
                      placeholder="http://127.0.0.1:8888"
                      className="w-full bg-[#f3ece0] rounded-lg px-3 py-2 text-[#4a3219]"
                    />
                    <p className="text-xs text-[#8c7358] mt-1">
                      Local search engine used by web_search. Start it with `just searxng` (needs
                      Docker). Leave empty to skip it; Tavily keyless and DuckDuckGo are the
                      fallbacks.
                    </p>
                  </div>
                </div>

                <div>
                  <div className="block text-[#4a3219] font-medium mb-1">Base URL</div>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={currentProvConfig.base_url}
                      onChange={(e) =>
                        updateProviderConfig(form.default_provider, {
                          base_url: e.target.value,
                        })
                      }
                      placeholder={activeProviderMeta.defaultBaseUrl}
                      className="flex-1 bg-[#f3ece0] rounded-lg px-3 py-2 text-[#4a3219]"
                    />
                    <button
                      type="button"
                      onClick={handleTest}
                      className="theta-btn-secondary shrink-0"
                    >
                      Test Connection
                    </button>
                  </div>
                </div>

                <div>
                  <label htmlFor="api-key" className="block text-[#4a3219] font-medium mb-1">
                    API Key{" "}
                    {activeProviderMeta.requiresApiKey ? (
                      <span className="text-[#8b6022] font-normal">(Required)</span>
                    ) : (
                      <span className="text-[#8c7358] font-normal">(Optional)</span>
                    )}
                  </label>
                  <div className="relative flex items-center">
                    <input
                      id="api-key"
                      type={showApiKey ? "text" : "password"}
                      required={activeProviderMeta.requiresApiKey}
                      value={currentProvConfig.api_key}
                      onChange={(e) =>
                        updateProviderConfig(form.default_provider, {
                          api_key: e.target.value,
                        })
                      }
                      placeholder={activeProviderMeta.apiKeyPlaceholder}
                      className="w-full bg-[#f3ece0] rounded-lg pl-3 pr-9 py-2 text-[#4a3219]"
                    />
                    <button
                      type="button"
                      onClick={() => setShowApiKey((s) => !s)}
                      title={showApiKey ? "Hide API Key" : "Show API Key"}
                      className="absolute right-2 p-1 text-[#70553a] hover:text-[#4a3219] rounded-md"
                    >
                      {showApiKey ? (
                        <EyeOff className="w-3.5 h-3.5" />
                      ) : (
                        <Eye className="w-3.5 h-3.5" />
                      )}
                    </button>
                  </div>
                </div>

                {testStatus && (
                  <div className="flex items-center gap-2 text-[#4a3219] bg-[#efe7d8] rounded-lg px-3 py-2">
                    <CheckCircle2 className="w-4 h-4 text-[#8b6022]" />
                    <span>{testStatus}</span>
                  </div>
                )}
                {testError && (
                  <div className="flex items-center gap-2 text-[#7f2217] bg-rose-50 rounded-lg px-3 py-2">
                    <AlertCircle className="w-4 h-4 shrink-0" />
                    <span className="truncate">{testError}</span>
                  </div>
                )}

                {unsavedKeyWarning && (
                  <div className="flex items-center gap-2 text-[#7f2217] bg-rose-50 rounded-lg px-3 py-2">
                    <AlertCircle className="w-4 h-4 shrink-0" />
                    <span className="flex-1">
                      Your API key is not saved. Save Settings to keep it, or discard it.
                    </span>
                    <button type="button" onClick={onClose} className="theta-btn-secondary">
                      Discard
                    </button>
                  </div>
                )}

                <div className="flex justify-end gap-2 pt-2">
                  <button type="button" onClick={requestClose} className="theta-btn-secondary">
                    Cancel
                  </button>
                  <button type="submit" className="theta-btn">
                    Save Settings
                  </button>
                </div>
              </>
            )}
          </form>
        )}

        {tab === "skills" && (
          <div className="space-y-4 pt-2 text-xs overflow-y-auto">
            <div className="flex items-center justify-between gap-2">
              <p className="text-[#8c7358]">
                Enabled skills are advertised in the system prompt and loaded on-demand via the{" "}
                <code className="text-[#8b6022] font-semibold">load_capability</code> tool.
              </p>
              <button
                type="button"
                onClick={() => {
                  setShowCreateSkill((s) => !s);
                  setSelectedSkill(null);
                }}
                className="theta-btn shrink-0"
              >
                <Plus className="w-3.5 h-3.5" />
                {showCreateSkill ? "Back to List" : "New Skill"}
              </button>
            </div>

            {showCreateSkill ? (
              <form
                onSubmit={handleCreateSkill}
                className="p-3.5 rounded-xl bg-[#f3ece0] space-y-2.5"
              >
                <div className="font-semibold text-[#4a3219]">Create Custom Skill</div>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label htmlFor="skill-name" className="block text-[#8c7358] mb-1">
                      Skill Name
                    </label>
                    <input
                      id="skill-name"
                      type="text"
                      value={skillName}
                      onChange={(e) => setSkillName(e.target.value)}
                      placeholder="e.g. api-designer"
                      className="w-full bg-white rounded-lg px-2.5 py-1.5 text-[#4a3219]"
                    />
                  </div>
                  <div>
                    <label htmlFor="scope" className="block text-[#8c7358] mb-1">
                      Scope
                    </label>
                    <select
                      id="scope"
                      value={skillScope}
                      onChange={(e) => setSkillScope(e.target.value as "global" | "project")}
                      className="w-full bg-white rounded-lg px-2.5 py-1.5 text-[#4a3219]"
                    >
                      <option value="global">Global</option>
                      <option value="project" disabled={!activeProjectId}>
                        Current Project
                      </option>
                    </select>
                  </div>
                </div>
                <div>
                  <label htmlFor="short-trigger-description" className="block text-[#8c7358] mb-1">
                    Short Trigger Description
                  </label>
                  <input
                    id="short-trigger-description"
                    type="text"
                    value={skillDesc}
                    onChange={(e) => setSkillDesc(e.target.value)}
                    placeholder="When should the model load this skill?"
                    className="w-full bg-white rounded-lg px-2.5 py-1.5 text-[#4a3219]"
                  />
                </div>
                <div>
                  <label
                    htmlFor="markdown-instructions-skill-md-body"
                    className="block text-[#8c7358] mb-1"
                  >
                    Markdown Instructions (SKILL.md body)
                  </label>
                  <textarea
                    id="markdown-instructions-skill-md-body"
                    rows={6}
                    value={skillBody}
                    onChange={(e) => setSkillBody(e.target.value)}
                    className="w-full bg-white rounded-lg p-2.5 text-[#4a3219] font-mono text-[11px]"
                  />
                </div>
                {skillError && <div className="text-[#7f2217]">{skillError}</div>}
                <div className="flex justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => setShowCreateSkill(false)}
                    className="theta-btn-secondary"
                  >
                    Cancel
                  </button>
                  <button type="submit" className="theta-btn">
                    Save Skill
                  </button>
                </div>
              </form>
            ) : (
              <div className="space-y-2">
                {skills.length === 0 && (
                  <div className="text-[#8c7358] py-4 text-center">
                    No skills configured yet. Click New Skill to add one.
                  </div>
                )}
                {skills.map((skill) => (
                  <div key={skill.name} className="p-3 rounded-xl bg-[#f3ece0] space-y-1.5">
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="font-mono font-semibold text-[#4a3219] truncate">
                          {skill.name}
                        </span>
                        <span className="px-2 py-0.5 rounded text-[10px] uppercase bg-[#e8decb] text-[#8c7358] font-medium">
                          {skill.source}
                        </span>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <button
                          type="button"
                          onClick={() =>
                            setSelectedSkill(selectedSkill?.name === skill.name ? null : skill)
                          }
                          className="theta-btn-secondary !p-1"
                          title="Inspect instructions"
                        >
                          <Eye className="w-3.5 h-3.5" />
                        </button>
                        <button
                          type="button"
                          onClick={async () => {
                            await api.deleteSkill(activeProjectId, skill.name);
                            await refreshSkills();
                          }}
                          className="theta-btn-secondary !p-1"
                          title="Delete skill"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                        <input
                          type="checkbox"
                          checked={skill.enabled}
                          onChange={(e) => toggleSkill(skill.name, e.target.checked)}
                          className="accent-[#8b6022] w-3.5 h-3.5 cursor-pointer"
                        />
                      </div>
                    </div>
                    <p className="text-[11px] text-[#5c4024] leading-relaxed">
                      {skill.description}
                    </p>
                    {selectedSkill?.name === skill.name && (
                      <pre className="mt-2 p-2.5 rounded-lg bg-[#2c1e14] text-[#faf7f1] text-[11px] font-mono whitespace-pre-wrap max-h-56 overflow-y-auto">
                        {skill.body}
                      </pre>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {tab === "mcp" && (
          <div className="space-y-4 pt-2 text-xs overflow-y-auto">
            <div className="flex items-center justify-between gap-2">
              <p className="text-[#8c7358]">
                Add stdio Model Context Protocol (MCP) servers. Tools exposed by enabled servers are
                automatically registered with the agent.
              </p>
              <button
                type="button"
                onClick={() => setShowCreateMcp((s) => !s)}
                className="theta-btn shrink-0"
              >
                <Plus className="w-3.5 h-3.5" />
                {showCreateMcp ? "Back to List" : "New Server"}
              </button>
            </div>

            {showCreateMcp ? (
              <form onSubmit={handleAddMcp} className="p-3.5 rounded-xl bg-[#f3ece0] space-y-2.5">
                <div className="font-semibold text-[#4a3219]">Add MCP Server</div>
                <div className="grid grid-cols-2 gap-2">
                  <input
                    type="text"
                    value={mcpName}
                    onChange={(e) => setMcpName(e.target.value)}
                    placeholder="Server name (e.g. filesystem)"
                    className="bg-white rounded-lg px-2.5 py-1.5 text-[#4a3219]"
                  />
                  <input
                    type="text"
                    value={mcpCommand}
                    onChange={(e) => setMcpCommand(e.target.value)}
                    placeholder="Command (e.g. npx, uvx, node)"
                    className="bg-white rounded-lg px-2.5 py-1.5 text-[#4a3219]"
                  />
                </div>
                <div>
                  <input
                    type="text"
                    value={mcpArgs}
                    onChange={(e) => setMcpArgs(e.target.value)}
                    placeholder="Arguments (space-separated)"
                    className="w-full bg-white rounded-lg px-2.5 py-1.5 text-[#4a3219]"
                  />
                </div>
                <div className="flex items-center gap-2">
                  <input
                    id="mcp-auto-approve"
                    type="checkbox"
                    checked={mcpAutoApprove}
                    onChange={(e) => setMcpAutoApprove(e.target.checked)}
                  />
                  <label htmlFor="mcp-auto-approve">
                    Run without approval (safe for read-only servers)
                  </label>
                </div>
                <div className="flex justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => setShowCreateMcp(false)}
                    className="theta-btn-secondary"
                  >
                    Cancel
                  </button>
                  <button type="submit" className="theta-btn">
                    Save Server
                  </button>
                </div>
              </form>
            ) : (
              <>
                {testError && (
                  <div className="text-[#7f2217] bg-rose-50 rounded-lg px-3 py-2">{testError}</div>
                )}

                {npxMissing && (
                  <div className="text-[#7f2217] bg-rose-50 rounded-lg px-3 py-2">
                    Node.js is required for this server. Install Node 20 or later.
                  </div>
                )}

                <div className="space-y-2">
                  {mcpServers.length === 0 && (
                    <div className="text-[#8c7358] py-4 text-center">
                      No MCP servers configured yet. Click New Server to add one.
                    </div>
                  )}
                  {mcpServers.map((srv) => (
                    <div key={srv.id} className="p-3 rounded-xl bg-[#f3ece0] space-y-2">
                      <div className="flex items-center justify-between">
                        <div>
                          <span className="font-semibold text-[#4a3219]">{srv.name}</span>
                          <span className="ml-2 font-mono text-[11px] text-[#8c7358]">
                            {srv.command} {srv.args.join(" ")}
                          </span>
                        </div>
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => handleTestMcp(srv)}
                            className="theta-btn-secondary !px-2.5 !py-1"
                          >
                            Discover Tools
                          </button>
                          <button
                            type="button"
                            onClick={async () => {
                              await api.deleteMcpServer(srv.id);
                              await refreshMcpServers();
                            }}
                            className="theta-btn-secondary !p-1.5"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 text-[11px] text-[#4a3219]">
                        <input
                          id={`mcp-auto-${srv.id}`}
                          type="checkbox"
                          checked={srv.auto_approve}
                          onChange={async (e) => {
                            await api.saveMcpServer({ ...srv, auto_approve: e.target.checked });
                            await refreshMcpServers();
                          }}
                        />
                        <label htmlFor={`mcp-auto-${srv.id}`}>Run without approval</label>
                      </div>
                      {mcpToolsPreview[srv.id] && (
                        <div className="text-[11px] text-[#8b6022] font-mono">
                          Tools:{" "}
                          {mcpToolsPreview[srv.id].map((t) => t.tool_name).join(", ") || "none"}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
