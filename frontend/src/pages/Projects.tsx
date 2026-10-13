import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Folder, File, Save, Search, ChevronLeft, GitCompare, Pencil, GitBranch, GitCommit, RefreshCw, PlusCircle } from 'lucide-react'
import Editor, { DiffEditor } from '@monaco-editor/react'
import { api, FileEntry, GitStatus, GitDiff, GitCommitResult } from '../services/api'

interface BrowseResponse {
  roots?: { path: string; exists: boolean }[]
  path?: string
  entries?: FileEntry[]
}

const LANG_BY_EXT: Record<string, string> = {
  py: 'python', ts: 'typescript', tsx: 'typescript', js: 'javascript', jsx: 'javascript',
  json: 'json', md: 'markdown', html: 'html', htm: 'html', css: 'css', scss: 'scss',
  yml: 'yaml', yaml: 'yaml', sql: 'sql', sh: 'shell', bash: 'shell', ps1: 'powershell',
  rs: 'rust', java: 'java', c: 'c', cpp: 'cpp', h: 'c', hpp: 'cpp', go: 'go',
  toml: 'ini', ini: 'ini', xml: 'xml', vue: 'html', txt: 'plaintext', env: 'plaintext',
}

function languageFor(path: string): string {
  const ext = path.split('.').pop()?.toLowerCase() || ''
  return LANG_BY_EXT[ext] || 'plaintext'
}

const GitPanel: React.FC = () => {
  const [commitMsg, setCommitMsg] = useState('')
  const [selected, setSelected] = useState<string[]>([])
  const [viewFile, setViewFile] = useState<string | null>(null)

  const { data: status, refetch: refetchStatus } = useQuery<GitStatus>({
    queryKey: ['git-status'],
    queryFn: async () => (await api.get('/projects/git/status')).data,
  })

  const { data: diff } = useQuery<GitDiff>({
    queryKey: ['git-diff', viewFile],
    queryFn: async () => (await api.get('/projects/git/diff', { params: viewFile ? { file: viewFile } : {} })).data,
    enabled: viewFile !== null,
  })

  const initMut = useMutation({
    mutationFn: async () => (await api.post('/projects/git/init')).data,
    onSuccess: () => refetchStatus(),
  })

  const commitMut = useMutation({
    mutationFn: async () =>
      (await api.post('/projects/git/commit', { message: commitMsg, files: selected })).data as GitCommitResult,
    onSuccess: (res) => {
      if (res.ok) {
        setCommitMsg('')
        setSelected([])
        refetchStatus()
      } else {
        window.alert(`Commit falló: ${res.error || ''}\n${res.output}`)
      }
    },
  })

  if (!status) return null

  if (!status.is_repo) {
    return (
      <div className="p-4 rounded-lg border dark:border-gray-700 flex items-center justify-between gap-3 flex-wrap">
        <div className="text-sm text-gray-600 dark:text-gray-400">
          Esta carpeta no es un repositorio Git.
          {status.error && <span className="block text-xs text-gray-400">{status.error}</span>}
        </div>
        <button onClick={() => initMut.mutate()} disabled={initMut.isPending} className="btn-secondary text-sm flex items-center gap-1">
          <PlusCircle className="w-4 h-4" /> Inicializar repositorio
        </button>
      </div>
    )
  }

  const changed = status.files || []
  const toggle = (p: string) =>
    setSelected((prev) => (prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p]))

  return (
    <div className="rounded-lg border dark:border-gray-700 divide-y dark:divide-gray-700">
      <div className="px-4 py-3 flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2 text-sm">
          <GitBranch className="w-4 h-4 text-nexus-500" />
          <span className="font-medium">{status.branch || 'sin rama'}</span>
          {status.ahead > 0 && <span className="text-xs text-gray-500">↑{status.ahead}</span>}
          {status.behind > 0 && <span className="text-xs text-gray-500">↓{status.behind}</span>}
          <span className="text-xs text-gray-500">{changed.length} cambio(s)</span>
        </div>
        <div className="flex items-center gap-2">
          <input
            value={commitMsg}
            onChange={(e) => setCommitMsg(e.target.value)}
            placeholder="Mensaje del commit…"
            className="px-3 py-1.5 text-sm rounded-lg border bg-transparent border-gray-300 dark:border-gray-600 w-64"
          />
          <button
            onClick={() => commitMut.mutate()}
            disabled={commitMut.isPending || !commitMsg.trim()}
            className="btn-primary text-sm flex items-center gap-1 disabled:opacity-50"
          >
            <GitCommit className="w-4 h-4" />{commitMut.isPending ? 'Creando…' : `Commit${selected.length ? ` (${selected.length})` : ' (todo)'}`}
          </button>
          <button onClick={() => refetchStatus()} className="p-2 rounded-lg border dark:border-gray-600" title="Actualizar">
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {changed.length === 0 && <div className="px-4 py-3 text-sm text-gray-500">Working tree limpio — sin cambios.</div>}

      {changed.map((f) => (
        <div key={f.path} className="px-4 py-2 flex items-center gap-3 text-sm hover:bg-gray-50 dark:hover:bg-gray-800/50">
          <input type="checkbox" checked={selected.includes(f.path)} onChange={() => toggle(f.path)} />
          <span className={`px-1.5 rounded text-[10px] font-mono ${f.worktree === '?' ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300' : 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300'}`}>
            {f.index}{f.worktree}
          </span>
          <span className="font-mono text-xs truncate flex-1">{f.path}</span>
          <span className="text-xs text-gray-500">{f.label}</span>
          <button onClick={() => setViewFile(viewFile === f.path ? null : f.path)} className="text-xs text-nexus-600 hover:underline flex items-center gap-1">
            <GitCompare className="w-3.5 h-3.5" /> {viewFile === f.path ? 'ocultar' : 'diff'}
          </button>
        </div>
      ))}

      {viewFile && (
        <div className="p-3">
          <div className="text-xs font-mono text-gray-500 mb-1">{viewFile}</div>
          {diff?.diff ? (
            <pre className="text-xs font-mono bg-gray-50 dark:bg-gray-900 p-3 rounded overflow-x-auto max-h-80 whitespace-pre-wrap">{diff.diff}</pre>
          ) : (
            <div className="text-xs text-gray-500">{diff?.error || (diff ? 'Sin diferencias (archivo nuevo o sin cambios staged).' : 'Cargando…')}</div>
          )}
        </div>
      )}
    </div>
  )
}

const ProjectsPage: React.FC = () => {
  const [currentPath, setCurrentPath] = useState<string | null>(null)
  const [selectedFile, setSelectedFile] = useState<string | null>(null)
  const [fileContent, setFileContent] = useState('')
  const [showDiff, setShowDiff] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<{ path: string; name: string; match: string; line?: number; preview?: string }[]>([])
  const queryClient = useQueryClient()
  const isDark = typeof document !== 'undefined' && document.documentElement.classList.contains('dark')

  const { data: browse } = useQuery<BrowseResponse>({
    queryKey: ['browse', currentPath],
    queryFn: async () =>
      (await api.get('/projects/browse', { params: currentPath ? { path: currentPath } : {} })).data,
  })

  const { data: file } = useQuery<{ path: string; content: string }>({
    queryKey: ['file', selectedFile],
    queryFn: async () => (await api.get('/projects/file', { params: { path: selectedFile } })).data,
    enabled: !!selectedFile,
  })

  React.useEffect(() => {
    if (file) {
      setFileContent(file.content)
      setShowDiff(false)
    }
  }, [file])

  const saveFile = useMutation({
    mutationFn: async ({ path, content }: { path: string; content: string }) =>
      (await api.post('/projects/file', { path, content })).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['file', selectedFile] }),
  })

  const doSearch = async () => {
    if (!searchQuery.trim()) return
    const res = await api.post('/projects/search', { query: searchQuery, max_results: 50 })
    setSearchResults(res.data.results)
  }

  const dirty = !!selectedFile && file !== undefined && fileContent !== file.content
  const lang = selectedFile ? languageFor(selectedFile) : 'plaintext'

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-3xl font-bold gradient-text">Proyectos</h1>
          <p className="text-gray-600 dark:text-gray-400">Explorador restringido a carpetas autorizadas</p>
        </div>
        <div className="flex gap-2 items-center">
          <input value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && doSearch()} placeholder="Buscar archivos…" className="px-3 py-2 text-sm rounded-lg border bg-transparent border-gray-300 dark:border-gray-600" />
          <button onClick={doSearch} className="btn-secondary text-sm flex items-center gap-1"><Search className="w-4 h-4" />Buscar</button>
        </div>
      </div>

      {searchResults.length > 0 && (
        <div className="p-3 rounded-lg border dark:border-gray-700 max-h-64 overflow-y-auto space-y-1">
          <div className="text-sm font-medium mb-1">{searchResults.length} resultados</div>
          {searchResults.map((r, i) => (
            <button key={i} onClick={() => { setSelectedFile(r.path); setSearchResults([]) }} className="block w-full text-left text-xs font-mono p-1.5 rounded hover:bg-gray-100 dark:hover:bg-gray-800">
              {r.path}{r.line ? `:${r.line}` : ''} <span className="text-gray-500">({r.match})</span>
              {r.preview && <span className="text-gray-500"> — {r.preview.slice(0, 100)}</span>}
            </button>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4" style={{ minHeight: '60vh' }}>
        <div className="space-y-4">
          <div className="rounded-lg border dark:border-gray-700 p-3 overflow-y-auto max-h-[40vh]">
            {currentPath && (
              <button onClick={() => { setCurrentPath(null); setSelectedFile(null) }} className="text-sm flex items-center gap-1 text-nexus-600 mb-2">
                <ChevronLeft className="w-4 h-4" /> Raíces autorizadas
              </button>
            )}
            {!currentPath && browse?.roots?.map((r) => (
              <button key={r.path} onClick={() => setCurrentPath(r.path)} className="w-full flex items-center gap-2 p-2 rounded hover:bg-gray-100 dark:hover:bg-gray-800 text-sm text-left">
                <Folder className="w-4 h-4 text-nexus-500" /> {r.path}
              </button>
            ))}
            {browse?.entries?.map((e) => (
              <button key={e.path} onClick={() => e.is_dir ? setCurrentPath(e.path) : setSelectedFile(e.path)} className={`w-full flex items-center gap-2 p-2 rounded hover:bg-gray-100 dark:hover:bg-gray-800 text-sm text-left ${selectedFile === e.path ? 'bg-nexus-50 dark:bg-nexus-900/30' : ''}`}>
                {e.is_dir ? <Folder className="w-4 h-4 text-nexus-500" /> : <File className="w-4 h-4 text-gray-400" />}
                <span className="truncate">{e.name}</span>
                {e.size !== null && <span className="ml-auto text-[10px] text-gray-400">{e.size} B</span>}
              </button>
            ))}
          </div>
          <GitPanel />
        </div>

        <div className="lg:col-span-2 rounded-lg border dark:border-gray-700 flex flex-col overflow-hidden">
          <div className="p-3 border-b dark:border-gray-700 flex items-center justify-between gap-2">
            <span className="text-sm font-mono truncate">
              {selectedFile || 'Ningún archivo seleccionado'}
              {dirty && <span className="ml-2 text-xs text-yellow-600 dark:text-yellow-400">● sin guardar</span>}
            </span>
            {selectedFile && (
              <div className="flex gap-2">
                <button
                  onClick={() => setShowDiff((v) => !v)}
                  className={`text-sm flex items-center gap-1 px-3 py-1.5 rounded-lg border ${showDiff ? 'border-nexus-500 text-nexus-600' : 'border-gray-300 dark:border-gray-600'}`}
                >
                  <GitCompare className="w-4 h-4" /> Diferencias
                </button>
                <button onClick={() => saveFile.mutate({ path: selectedFile, content: fileContent })} disabled={saveFile.isPending || !dirty} className="btn-primary text-sm flex items-center gap-1 disabled:opacity-50">
                  <Save className="w-4 h-4" />{saveFile.isPending ? 'Guardando…' : 'Guardar'}
                </button>
              </div>
            )}
          </div>
          <div className="flex-1 min-h-[50vh]">
            {!selectedFile && (
              <div className="h-full flex items-center justify-center text-gray-500 text-sm gap-2">
                <Pencil className="w-4 h-4" /> Selecciona un archivo para editarlo
              </div>
            )}
            {selectedFile && showDiff && (
              <DiffEditor
                original={file?.content ?? ''}
                modified={fileContent}
                language={lang}
                theme={isDark ? 'vs-dark' : 'light'}
                options={{ readOnly: true, renderSideBySide: true, minimap: { enabled: false } }}
                height="50vh"
              />
            )}
            {selectedFile && !showDiff && (
              <Editor
                path={selectedFile}
                value={fileContent}
                language={lang}
                theme={isDark ? 'vs-dark' : 'light'}
                onChange={(v?: string) => setFileContent(v ?? '')}
                options={{ minimap: { enabled: false }, fontSize: 13, automaticLayout: true, scrollBeyondLastLine: false }}
                height="50vh"
              />
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default ProjectsPage
