import { useState, useEffect } from 'react';
import { loadToken, getAuthHeader } from '../lib/auth';
import LoadingLogo from '../components/LoadingLogo';

function IDEPage() {
  const [projects, setProjects] = useState([]);
  const [currentProject, setCurrentProject] = useState(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [assignmentPrompt, setAssignmentPrompt] = useState('');
  const [projectTitle, setProjectTitle] = useState('');
  const [templateFile, setTemplateFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [content, setContent] = useState('');
  const [aiResponse, setAiResponse] = useState(null);
  const [contentSuggestions, setContentSuggestions] = useState([]); // Actual content improvements
  const [chatMessages, setChatMessages] = useState([]);
  const [chatInput, setChatInput] = useState('');
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [saveStatus, setSaveStatus] = useState('saved'); // 'saved', 'saving', 'unsaved'
  const [folders, setFolders] = useState([]);
  const [showCreateFolderModal, setShowCreateFolderModal] = useState(false);
  const [newFolderName, setNewFolderName] = useState('');
  const [expandedFolders, setExpandedFolders] = useState(new Set());
  const [expandedReasons, setExpandedReasons] = useState(new Set());
  const [loadingProjects, setLoadingProjects] = useState(true);
  const [isGeneratingSuggestions, setIsGeneratingSuggestions] = useState(false);
  const [lastSuggestionTime, setLastSuggestionTime] = useState(0);
  const [suggestionCooldown, setSuggestionCooldown] = useState(0);

  useEffect(() => {
    loadProjects();
  }, []);

  const loadProjects = async () => {
    setLoadingProjects(true);
    try {
      const token = loadToken();
      if (!token) {
        setLoadingProjects(false);
        return;
      }

      const response = await fetch('http://localhost:8000/api/ide/projects', {
        headers: getAuthHeader()
      });

      if (response.ok) {
        const data = await response.json();
        setProjects(data);
      }
    } catch (error) {
      console.error('Failed to load projects:', error);
    } finally {
      setLoadingProjects(false);
    }
  };

  const deleteProject = async (projectId, e) => {
    e.stopPropagation(); // Prevent opening the project when clicking delete
    if (!confirm('Delete this assignment? This action cannot be undone.')) return;

    try {
      const response = await fetch(`http://localhost:8000/api/ide/projects/${projectId}`, {
        method: 'DELETE',
        headers: getAuthHeader()
      });

      if (response.ok) {
        setProjects(prev => prev.filter(p => p.id !== projectId));
        // If deleted project was currently open, close it
        if (currentProject?.id === projectId) {
          setCurrentProject(null);
          setContent('');
        }
        alert('Assignment deleted successfully');
      } else {
        alert('Failed to delete assignment');
      }
    } catch (error) {
      console.error('Failed to delete project:', error);
      alert('Failed to delete assignment');
    }
  };

  const createProject = async () => {
    if (!assignmentPrompt.trim() && !templateFile) {
      alert('Please enter an assignment prompt or upload a template file');
      return;
    }

    setLoading(true);
    try {
      const token = loadToken();
      if (!token) {
        alert('Please log in first');
        return;
      }

      let initialContent = '';

      // If template file provided, read it first
      if (templateFile) {
        initialContent = await readFileContent(templateFile);
      }

      const response = await fetch('http://localhost:8000/api/ide/projects/create', {
        method: 'POST',
        headers: {
          ...getAuthHeader(),
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          assignment_prompt: assignmentPrompt || `Work on uploaded file: ${templateFile?.name}`,
          title: projectTitle || templateFile?.name || null,
          initial_content: initialContent
        })
      });

      if (response.ok) {
        const project = await response.json();
        setProjects([project, ...projects]);
        setCurrentProject(project);
        setContent(initialContent || project.current_content || '');
        setShowCreateModal(false);
        setAssignmentPrompt('');
        setProjectTitle('');
        setTemplateFile(null);
      } else {
        const error = await response.json();
        alert(`Failed to create project: ${error.detail}`);
      }
    } catch (error) {
      console.error('Failed to create project:', error);
      alert('Failed to create project. Make sure the backend is running.');
    } finally {
      setLoading(false);
    }
  };

  const readFileContent = (file) => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = (e) => resolve(e.target.result);
      reader.onerror = reject;
      reader.readAsText(file);
    });
  };

  const openProject = async (projectId) => {
    try {
      const token = loadToken();
      if (!token) return;

      const response = await fetch(`http://localhost:8000/api/ide/projects/${projectId}`, {
        headers: getAuthHeader()
      });

      if (response.ok) {
        const project = await response.json();
        setCurrentProject(project);
        setContent(project.current_content || '');
      }
    } catch (error) {
      console.error('Failed to open project:', error);
    }
  };

  const saveContent = async () => {
    if (!currentProject) return;

    try {
      const token = loadToken();
      if (!token) return;

      const response = await fetch(`http://localhost:8000/api/ide/projects/${currentProject.id}/content`, {
        method: 'PUT',
        headers: {
          ...getAuthHeader(),
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          project_id: currentProject.id,
          content: content
        })
      });

      if (response.ok) {
        const result = await response.json();
        console.log('Saved:', result);
      }
    } catch (error) {
      console.error('Failed to save:', error);
    }
  };

  const suggestNext = async () => {
    if (!currentProject) return;

    setLoading(true);
    try {
      const token = loadToken();
      if (!token) return;

      const response = await fetch('http://localhost:8000/api/ide/suggest-next', {
        method: 'POST',
        headers: {
          ...getAuthHeader(),
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          project_id: currentProject.id,
          current_text: content
        })
      });

      if (response.ok) {
        const result = await response.json();
        setAiResponse({
          type: 'suggestions',
          data: result.suggestions
        });
      }
    } catch (error) {
      console.error('Failed to get suggestions:', error);
    } finally {
      setLoading(false);
    }
  };

  const generateScaffold = async () => {
    if (!currentProject) return;

    setLoading(true);
    try {
      const token = loadToken();
      if (!token) return;

      const userRequest = prompt('What would you like to generate? (e.g., "Create an outline for the introduction")');
      if (!userRequest) {
        setLoading(false);
        return;
      }

      const response = await fetch('http://localhost:8000/api/ide/generate', {
        method: 'POST',
        headers: {
          ...getAuthHeader(),
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          project_id: currentProject.id,
          user_request: userRequest,
          current_text: content,
          generation_mode: 'scaffold'
        })
      });

      if (response.ok) {
        const result = await response.json();
        setAiResponse({
          type: 'generation',
          data: result
        });
      }
    } catch (error) {
      console.error('Failed to generate:', error);
    } finally {
      setLoading(false);
    }
  };

  const reviewWork = async () => {
    if (!currentProject) return;

    setLoading(true);
    try {
      const token = loadToken();
      if (!token) return;

      const response = await fetch('http://localhost:8000/api/ide/review', {
        method: 'POST',
        headers: {
          ...getAuthHeader(),
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          project_id: currentProject.id,
          content: content
        })
      });

      if (response.ok) {
        const result = await response.json();
        setAiResponse({
          type: 'review',
          data: result
        });
      }
    } catch (error) {
      console.error('Failed to review:', error);
    } finally {
      setLoading(false);
    }
  };

  // Auto-save content as user types
  useEffect(() => {
    if (!currentProject) return;

    setSaveStatus('unsaved');

    const saveTimer = setTimeout(async () => {
      setSaveStatus('saving');
      await saveContent();
      setSaveStatus('saved');
    }, 1000); // Auto-save 1s after user stops typing

    return () => clearTimeout(saveTimer);
  }, [content, currentProject]);

  // Update cooldown timer
  useEffect(() => {
    if (suggestionCooldown > 0) {
      const timer = setTimeout(() => {
        setSuggestionCooldown(suggestionCooldown - 1);
      }, 1000);
      return () => clearTimeout(timer);
    }
  }, [suggestionCooldown]);

  const refreshContentSuggestions = async () => {
    if (!currentProject) return;

    // Check rate limiting (2 requests per minute = 30 seconds cooldown)
    const now = Date.now();
    const timeSinceLastRequest = now - lastSuggestionTime;
    const cooldownMs = 30000; // 30 seconds

    if (timeSinceLastRequest < cooldownMs) {
      const remainingSeconds = Math.ceil((cooldownMs - timeSinceLastRequest) / 1000);
      alert(`Please wait ${remainingSeconds} seconds before requesting suggestions again.`);
      return;
    }

    if (content.length < 50) {
      alert('Please write at least 50 characters before requesting suggestions.');
      return;
    }

    setIsGeneratingSuggestions(true);
    setLastSuggestionTime(now);
    setSuggestionCooldown(30);

    try {
      const token = loadToken();
      if (!token) return;

      const response = await fetch('http://localhost:8000/api/ide/improve-content', {
        method: 'POST',
        headers: {
          ...getAuthHeader(),
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          project_id: currentProject.id,
          current_text: content
        })
      });

      if (response.ok) {
        const result = await response.json();
        const newSuggestions = result.suggestions || [];
        setContentSuggestions(newSuggestions);
      }
    } catch (error) {
      console.error('Failed to refresh content suggestions:', error);
    } finally {
      setIsGeneratingSuggestions(false);
    }
  };

  const acceptSuggestion = (suggestion) => {
    // Replace the original text with the improved version
    setContent(content.replace(suggestion.original, suggestion.improved));
    // Remove this suggestion from the list
    setContentSuggestions(prev => prev.filter(s => s.original !== suggestion.original));
  };

  const rejectSuggestion = (suggestion) => {
    // Remove this suggestion from the list
    setContentSuggestions(prev => prev.filter(s => s.original !== suggestion.original));
  };

  const applyChatContent = (suggestionText) => {
    setContent(prev => prev + '\n\n' + suggestionText);
  };

  const sendChatMessage = async () => {
    if (!chatInput.trim() || !currentProject) return;

    const userMessage = chatInput;
    setChatMessages(prev => [...prev, { role: 'user', content: userMessage }]);
    setChatInput('');
    setIsGenerating(true);

    try {
      const token = loadToken();
      if (!token) return;

      const response = await fetch('http://localhost:8000/api/ide/chat', {
        method: 'POST',
        headers: {
          ...getAuthHeader(),
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          project_id: currentProject.id,
          message: userMessage,
          current_text: content,
          chat_history: chatMessages
        })
      });

      if (response.ok) {
        const result = await response.json();
        setChatMessages(prev => [...prev, {
          role: 'assistant',
          content: result.response,
          action: result.action,
          generated_text: result.generated_text
        }]);
      }
    } catch (error) {
      console.error('Failed to send chat message:', error);
      setChatMessages(prev => [...prev, { role: 'assistant', content: 'Sorry, I encountered an error. Please try again.' }]);
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <div className="min-h-screen bg-black">
      {/* Header */}
      <div className="bg-black border-b border-rose-950/50 px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={() => window.location.href = '/'}
              className="text-zinc-400 hover:text-pink-400 transition-colors"
              title="Back to StudySphere"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
              </svg>
            </button>
            <h1 className="text-2xl font-bold bg-gradient-to-r from-amber-400 to-pink-400 bg-clip-text text-transparent">
              Assignments
            </h1>
          </div>
          <button
            onClick={() => setShowCreateModal(true)}
            className="bg-gradient-to-r from-orange-500 via-amber-500 to-pink-500 text-white px-4 py-2 rounded-lg hover:from-orange-400 hover:via-amber-400 hover:to-yellow-400 transition-all shadow-lg shadow-rose-600/25"
          >
            + New Assignment
          </button>
        </div>
      </div>

      <div className="flex h-[calc(100vh-73px)]">
        {/* Sidebar - Assignments List */}
        <div className="w-64 bg-zinc-950 border-r border-rose-950/40 overflow-y-auto">
          <div className="p-4">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold bg-gradient-to-r from-orange-400 via-amber-400 to-pink-400 bg-clip-text text-transparent">
                Your Assignments
              </h2>
              <button
                onClick={() => setShowCreateFolderModal(true)}
                className="text-zinc-400 hover:text-pink-400 transition-colors"
                title="Create folder"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 13h6m-3-3v6m-9 1V7a2 2 0 012-2h6l2 2h6a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z" />
                </svg>
              </button>
            </div>

            {loadingProjects ? (
              <div className="flex items-center justify-center py-12">
                <LoadingLogo size="md" />
              </div>
            ) : projects.length === 0 && folders.length === 0 ? (
              <div className="text-center py-8">
                <p className="text-sm text-zinc-500 mb-2">No assignments yet.</p>
                <p className="text-xs text-zinc-600">Try creating one to get started!</p>
              </div>
            ) : (
              <div className="space-y-1">
                {/* Folders */}
                {folders.map(folder => {
                  const folderProjects = projects.filter(p => p.folder_id === folder.id);
                  const isExpanded = expandedFolders.has(folder.id);

                  return (
                    <div key={folder.id}>
                      <button
                        onClick={() => {
                          const newExpanded = new Set(expandedFolders);
                          if (isExpanded) {
                            newExpanded.delete(folder.id);
                          } else {
                            newExpanded.add(folder.id);
                          }
                          setExpandedFolders(newExpanded);
                        }}
                        className="w-full text-left p-2 rounded flex items-center gap-2 text-zinc-300 hover:bg-zinc-900/50 transition-colors"
                      >
                        <svg className={`w-4 h-4 transition-transform ${isExpanded ? 'rotate-90' : ''}`} fill="currentColor" viewBox="0 0 20 20">
                          <path fillRule="evenodd" d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z" clipRule="evenodd" />
                        </svg>
                        <svg className="w-4 h-4 text-pink-400" fill="currentColor" viewBox="0 0 20 20">
                          <path d="M2 6a2 2 0 012-2h5l2 2h5a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" />
                        </svg>
                        <span className="text-sm font-medium">{folder.name}</span>
                        <span className="text-xs text-zinc-600 ml-auto">{folderProjects.length}</span>
                      </button>

                      {isExpanded && (
                        <div className="ml-6 mt-1 space-y-1">
                          {folderProjects.map(project => (
                            <div
                              key={project.id}
                              className="group relative"
                            >
                              <button
                                onClick={() => openProject(project.id)}
                                className={`w-full text-left p-2 rounded-lg border transition-all ${
                                  currentProject?.id === project.id
                                    ? 'bg-rose-950/60 border-amber-700/50'
                                    : 'bg-zinc-900/30 border-zinc-800/50 hover:bg-zinc-900/50 hover:border-amber-900/40'
                                }`}
                              >
                                <div className="font-medium text-sm text-zinc-200 truncate pr-16">
                                  {project.title}
                                </div>
                                <div className="text-xs text-zinc-500 mt-1">
                                  {project.assignment_type}
                                </div>
                              </button>
                              <button
                                onClick={(e) => deleteProject(project.id, e)}
                                className="absolute right-2 top-2 opacity-0 group-hover:opacity-100 text-xs px-2 py-1 rounded bg-red-950/50 text-red-400 border border-red-800/30 hover:bg-red-900/50 transition-all duration-200"
                              >
                                Delete
                              </button>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}

                {/* Assignments without folders */}
                {projects.filter(p => !p.folder_id).map(project => (
                  <div
                    key={project.id}
                    className="group relative"
                  >
                    <button
                      onClick={() => openProject(project.id)}
                      className={`w-full text-left p-3 rounded-lg border transition-all ${
                        currentProject?.id === project.id
                          ? 'bg-rose-950/60 border-amber-700/50'
                          : 'bg-zinc-900/50 border-zinc-800 hover:bg-zinc-900 hover:border-amber-900/40'
                      }`}
                    >
                      <div className="font-medium text-sm text-zinc-200 truncate pr-16">
                        {project.title}
                      </div>
                      <div className="text-xs text-zinc-500 mt-1">
                        {project.assignment_type}
                      </div>
                    </button>
                    <button
                      onClick={(e) => deleteProject(project.id, e)}
                      className="absolute right-2 top-2 opacity-0 group-hover:opacity-100 text-xs px-2 py-1 rounded bg-red-950/50 text-red-400 border border-red-800/30 hover:bg-red-900/50 transition-all duration-200"
                    >
                      Delete
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Main Editor Area */}
        <div className="flex-1 flex">
          {currentProject ? (
            <>
              {/* Editor */}
              <div className="flex-1 flex flex-col bg-zinc-950 border-r border-rose-950/40">
                <div className="bg-zinc-900 border-b border-rose-950/40 px-4 py-2 flex items-center justify-between">
                  <div>
                    <h2 className="font-semibold text-zinc-100">{currentProject.title}</h2>
                    <p className="text-xs text-zinc-500">
                      {currentProject.assignment_type} • {content.split(/\s+/).filter(w => w).length} words
                    </p>
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="flex items-center gap-1.5 text-xs">
                      {saveStatus === 'saved' && (
                        <>
                          <svg className="w-4 h-4 text-amber-400" fill="currentColor" viewBox="0 0 20 20">
                            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                          </svg>
                          <span className="text-zinc-400">Saved</span>
                        </>
                      )}
                      {saveStatus === 'saving' && (
                        <>
                          <svg className="w-4 h-4 text-amber-400 animate-spin" fill="none" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                          </svg>
                          <span className="text-zinc-400">Saving...</span>
                        </>
                      )}
                      {saveStatus === 'unsaved' && (
                        <>
                          <svg className="w-4 h-4 text-zinc-500" fill="currentColor" viewBox="0 0 20 20">
                            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                          </svg>
                          <span className="text-zinc-500">Unsaved</span>
                        </>
                      )}
                    </div>
                  </div>
                </div>

                <textarea
                  value={content}
                  onChange={(e) => setContent(e.target.value)}
                  className="flex-1 p-6 font-mono text-sm resize-none focus:outline-none bg-black text-zinc-100 placeholder-zinc-600"
                  placeholder="Start writing your assignment here..."
                />
              </div>

              {/* Right Sidebar - Sphere Panels */}
              <div className="w-96 flex flex-col bg-zinc-950">
                {/* Content Improvement Suggestions Panel */}
                <div className="h-1/2 flex flex-col border-b border-rose-950/40">
                  <div className="p-3 border-b border-amber-900/50 bg-gradient-to-r from-orange-500 to-amber-500 text-white">
                    <div className="flex items-center justify-between">
                      <div>
                        <h3 className="font-semibold text-sm">Content Improvements</h3>
                        <p className="text-xs opacity-90">
                          {contentSuggestions.length > 0
                            ? `${contentSuggestions.length} suggestion${contentSuggestions.length !== 1 ? 's' : ''}`
                            : 'Click button to get suggestions'}
                        </p>
                      </div>
                      <button
                        onClick={refreshContentSuggestions}
                        disabled={isGeneratingSuggestions || suggestionCooldown > 0}
                        className="bg-white/20 hover:bg-white/30 disabled:bg-white/10 disabled:cursor-not-allowed text-white px-3 py-1.5 rounded text-xs font-medium transition-all flex items-center gap-1.5"
                        title={suggestionCooldown > 0 ? `Wait ${suggestionCooldown}s` : 'Generate suggestions'}
                      >
                        {isGeneratingSuggestions ? (
                          <LoadingLogo size="xs" />
                        ) : suggestionCooldown > 0 ? (
                          <span>{suggestionCooldown}s</span>
                        ) : (
                          <>
                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                            </svg>
                            Generate
                          </>
                        )}
                      </button>
                    </div>
                  </div>

                <div className="flex-1 overflow-y-auto p-3 space-y-2 bg-zinc-900/50">
                  {contentSuggestions.length > 0 ? (
                    contentSuggestions.slice(0, 5).map((suggestion, idx) => {
                      const isReasonExpanded = expandedReasons.has(idx);

                      return (
                        <div key={idx} className="bg-zinc-900 border border-amber-900/50 rounded-lg p-2.5">
                          <div className="mb-2">
                            <div className="text-xs text-zinc-500 mb-1">
                              <span className="line-through">"{suggestion.original.substring(0, 50)}{suggestion.original.length > 50 ? '...' : ''}"</span>
                            </div>
                            <div className="text-sm text-zinc-100">
                              "{suggestion.improved.substring(0, 80)}{suggestion.improved.length > 80 ? '...' : ''}"
                            </div>
                          </div>

                          {isReasonExpanded && (
                            <div className="mb-2 text-xs text-zinc-400 bg-zinc-950/50 rounded px-2 py-1.5">
                              {suggestion.reason}
                            </div>
                          )}

                          <div className="flex gap-1.5">
                            <button
                              onClick={() => acceptSuggestion(suggestion)}
                              className="flex-1 bg-gradient-to-r from-orange-500 to-amber-500 text-white px-2 py-1 rounded text-xs font-medium hover:from-rose-400 hover:to-amber-400 transition-all"
                            >
                              Accept
                            </button>
                            <button
                              onClick={() => {
                                const newExpanded = new Set(expandedReasons);
                                if (isReasonExpanded) {
                                  newExpanded.delete(idx);
                                } else {
                                  newExpanded.add(idx);
                                }
                                setExpandedReasons(newExpanded);
                              }}
                              className="px-2 py-1 bg-zinc-800 text-zinc-400 rounded text-xs hover:bg-zinc-700 transition-colors"
                              title={isReasonExpanded ? "Hide reason" : "See why"}
                            >
                              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                              </svg>
                            </button>
                            <button
                              onClick={() => rejectSuggestion(suggestion)}
                              className="px-2 py-1 bg-zinc-800 text-zinc-400 rounded text-xs hover:bg-zinc-700 transition-colors"
                              title="Reject"
                            >
                              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                              </svg>
                            </button>
                          </div>
                        </div>
                      );
                    })
                  ) : (
                    <div className="text-center text-zinc-500 py-8">
                      <svg className="w-12 h-12 mx-auto mb-3 text-zinc-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                      </svg>
                      <p className="text-sm">No suggestions yet</p>
                      <p className="text-xs mt-1">Write at least 50 characters, then click Generate</p>
                    </div>
                  )}
                </div>
              </div>

                {/* Chat Panel */}
                <div className="h-1/2 flex flex-col">
                  <div className="p-3 border-b border-amber-900/50 bg-gradient-to-r from-amber-500 to-pink-500 text-white flex items-center gap-2">
                    <LoadingLogo size="sm" />
                    <div>
                      <h3 className="font-semibold text-sm">Chat Assistant</h3>
                      <p className="text-xs opacity-90">Ask me anything</p>
                    </div>
                  </div>

                  <>
                    <div className="flex-1 overflow-y-auto p-3 space-y-3 bg-zinc-900/50 scrollbar-rose">
                      {chatMessages.length === 0 ? (
                        <div className="text-center text-zinc-500 text-sm py-8">
                          <p className="mb-4">Ask me anything!</p>
                          <div className="space-y-2">
                            <button
                              onClick={() => { setChatInput('Help me finish this essay'); setTimeout(sendChatMessage, 100); }}
                              className="block w-full text-xs bg-zinc-900 border border-zinc-800 rounded p-2 hover:bg-zinc-800 text-left text-zinc-300"
                            >
                              "Help me finish this essay"
                            </button>
                            <button
                              onClick={() => { setChatInput('Make this more detailed'); setTimeout(sendChatMessage, 100); }}
                              className="block w-full text-xs bg-zinc-900 border border-zinc-800 rounded p-2 hover:bg-zinc-800 text-left text-zinc-300"
                            >
                              "Make this more detailed"
                            </button>
                            <button
                              onClick={() => { setChatInput('Write a conclusion'); setTimeout(sendChatMessage, 100); }}
                              className="block w-full text-xs bg-zinc-900 border border-zinc-800 rounded p-2 hover:bg-zinc-800 text-left text-zinc-300"
                            >
                              "Write a conclusion"
                            </button>
                          </div>
                        </div>
                      ) : (
                        chatMessages.map((msg, idx) => (
                          <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                            <div className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
                              msg.role === 'user'
                                ? 'bg-gradient-to-r from-amber-500 to-pink-500 text-white'
                                : 'bg-zinc-900 border border-zinc-800 text-zinc-100'
                            }`}>
                              <p className="whitespace-pre-wrap">{msg.content}</p>
                              {msg.action === 'insert' && msg.generated_text && (
                                <div className="mt-3 space-y-2">
                                  <div className="text-xs text-zinc-400 font-semibold">Preview:</div>
                                  <div className="bg-zinc-950/50 border border-amber-900/30 rounded p-2 text-xs max-h-32 overflow-y-auto">
                                    <p className="whitespace-pre-wrap text-zinc-300">{msg.generated_text}</p>
                                  </div>
                                  <div className="flex gap-2">
                                    <button
                                      onClick={() => {
                                        applyChatContent(msg.generated_text);
                                        // Mark as applied by removing the action
                                        setChatMessages(prev => prev.map((m, i) =>
                                          i === idx ? { ...m, action: 'applied' } : m
                                        ));
                                      }}
                                      className="flex-1 bg-gradient-to-r from-orange-500 to-amber-500 text-white px-3 py-1.5 rounded text-xs font-medium hover:from-rose-400 hover:to-amber-400 transition-all"
                                    >
                                      Accept & Insert
                                    </button>
                                    <button
                                      onClick={() => {
                                        // Mark as declined by removing the action
                                        setChatMessages(prev => prev.map((m, i) =>
                                          i === idx ? { ...m, action: 'declined' } : m
                                        ));
                                      }}
                                      className="flex-1 bg-zinc-800 text-zinc-300 px-3 py-1.5 rounded text-xs font-medium hover:bg-zinc-700 transition-colors"
                                    >
                                      Decline
                                    </button>
                                  </div>
                                </div>
                              )}
                              {msg.action === 'applied' && (
                                <div className="mt-2 text-xs text-pink-400 flex items-center gap-1">
                                  <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                                  </svg>
                                  <span>Inserted into document</span>
                                </div>
                              )}
                              {msg.action === 'declined' && (
                                <div className="mt-2 text-xs text-zinc-500">
                                  <span>Suggestion declined</span>
                                </div>
                              )}
                            </div>
                          </div>
                        ))
                      )}
                      {isGenerating && (
                        <div className="flex justify-start">
                          <div className="bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2">
                            <LoadingLogo size="sm" />
                          </div>
                        </div>
                      )}
                    </div>

                    <div className="p-3 border-t border-amber-900/50 bg-zinc-950 rounded-b-lg">
                      <div className="flex gap-2">
                        <input
                          type="text"
                          value={chatInput}
                          onChange={(e) => setChatInput(e.target.value)}
                          onKeyPress={(e) => e.key === 'Enter' && sendChatMessage()}
                          placeholder="Ask Sphere anything..."
                          className="flex-1 text-sm bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-zinc-100 placeholder-zinc-600 focus:outline-none focus:ring-2 focus:ring-amber-500/50"
                          disabled={isGenerating}
                        />
                        <button
                          onClick={sendChatMessage}
                          disabled={!chatInput.trim() || isGenerating}
                          className="bg-gradient-to-r from-amber-500 to-pink-500 text-white px-4 py-2 rounded hover:from-pink-400 hover:to-amber-400 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                          </svg>
                        </button>
                      </div>
                    </div>
                  </>
                </div>
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center text-zinc-500 bg-black">
              <div className="text-center">
                <p className="text-lg mb-2">No assignment selected</p>
                <p className="text-sm">Create a new assignment or select an existing one</p>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Create Assignment Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-50">
          <div className="bg-zinc-950 border border-rose-950/50 rounded-lg p-6 w-full max-w-2xl">
            <h2 className="text-xl font-bold mb-4 bg-gradient-to-r from-orange-400 via-amber-400 to-pink-400 bg-clip-text text-transparent">
              Create New Assignment
            </h2>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-zinc-400 mb-1">
                  Assignment Title (optional)
                </label>
                <input
                  type="text"
                  value={projectTitle}
                  onChange={(e) => setProjectTitle(e.target.value)}
                  className="w-full bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 text-zinc-100 placeholder-zinc-600 focus:outline-none focus:ring-2 focus:ring-amber-500/50"
                  placeholder="My Essay"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-zinc-400 mb-1">
                  Assignment Prompt {!templateFile && '*'}
                </label>
                <textarea
                  value={assignmentPrompt}
                  onChange={(e) => setAssignmentPrompt(e.target.value)}
                  className="w-full bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 h-32 text-zinc-100 placeholder-zinc-600 focus:outline-none focus:ring-2 focus:ring-amber-500/50"
                  placeholder="Paste your assignment prompt here. For example:&#10;&#10;Write a 5-paragraph essay about climate change..."
                  disabled={!!templateFile}
                />
              </div>

              <div className="text-center text-zinc-500 text-sm">OR</div>

              <div>
                <label className="block text-sm font-medium text-zinc-400 mb-1">
                  Upload Template/Homework File
                </label>
                <div className="border-2 border-dashed border-zinc-800 rounded-lg p-4 text-center hover:border-amber-900 transition-colors">
                  {templateFile ? (
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <svg className="w-8 h-8 text-pink-400" fill="currentColor" viewBox="0 0 20 20">
                          <path fillRule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z" clipRule="evenodd" />
                        </svg>
                        <div className="text-left">
                          <p className="text-sm font-medium text-zinc-100">{templateFile.name}</p>
                          <p className="text-xs text-zinc-500">{(templateFile.size / 1024).toFixed(1)} KB</p>
                        </div>
                      </div>
                      <button
                        onClick={() => setTemplateFile(null)}
                        className="text-amber-400 hover:text-rose-300"
                      >
                        <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                          <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                        </svg>
                      </button>
                    </div>
                  ) : (
                    <div>
                      <svg className="w-12 h-12 mx-auto text-zinc-600 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                      </svg>
                      <p className="text-sm text-zinc-400 mb-2">Upload .txt, .pdf, .docx, or other document</p>
                      <input
                        type="file"
                        id="template-upload"
                        className="hidden"
                        accept=".txt,.pdf,.doc,.docx,.md"
                        onChange={(e) => setTemplateFile(e.target.files[0])}
                      />
                      <label
                        htmlFor="template-upload"
                        className="inline-block px-4 py-2 bg-gradient-to-r from-amber-400 to-pink-400 text-white rounded-lg cursor-pointer hover:from-rose-300 hover:to-amber-300 text-sm transition-all"
                      >
                        Choose File
                      </label>
                    </div>
                  )}
                </div>
                <p className="text-xs text-zinc-500 mt-1">
                  Upload your homework, worksheet, or template to work on it directly with Sphere assistance
                </p>
              </div>
            </div>

            <div className="flex justify-end space-x-3 mt-6">
              <button
                onClick={() => {
                  setShowCreateModal(false);
                  setAssignmentPrompt('');
                  setProjectTitle('');
                  setTemplateFile(null);
                }}
                className="px-4 py-2 border border-zinc-800 rounded-lg text-zinc-300 hover:bg-zinc-900 transition-colors"
                disabled={loading}
              >
                Cancel
              </button>
              <button
                onClick={createProject}
                disabled={loading || (!assignmentPrompt.trim() && !templateFile)}
                className="px-4 py-2 bg-gradient-to-r from-amber-400 to-pink-400 text-white rounded-lg hover:from-rose-300 hover:to-amber-300 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
              >
                {loading ? 'Creating...' : 'Create Assignment'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Create Folder Modal */}
      {showCreateFolderModal && (
        <div className="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-50">
          <div className="bg-zinc-950 border border-rose-950/50 rounded-lg p-6 w-full max-w-md">
            <h2 className="text-xl font-bold mb-4 bg-gradient-to-r from-orange-400 via-amber-400 to-pink-400 bg-clip-text text-transparent">
              Create New Folder
            </h2>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-zinc-400 mb-1">
                  Folder Name
                </label>
                <input
                  type="text"
                  value={newFolderName}
                  onChange={(e) => setNewFolderName(e.target.value)}
                  className="w-full bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 text-zinc-100 placeholder-zinc-600 focus:outline-none focus:ring-2 focus:ring-amber-500/50"
                  placeholder="Math Homework"
                  autoFocus
                />
              </div>
            </div>

            <div className="flex justify-end space-x-3 mt-6">
              <button
                onClick={() => {
                  setShowCreateFolderModal(false);
                  setNewFolderName('');
                }}
                className="px-4 py-2 border border-zinc-800 rounded-lg text-zinc-300 hover:bg-zinc-900 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  // TODO: Implement folder creation
                  const newFolder = {
                    id: Date.now(), // Temporary ID
                    name: newFolderName,
                    color: 'teal'
                  };
                  setFolders([...folders, newFolder]);
                  setShowCreateFolderModal(false);
                  setNewFolderName('');
                }}
                disabled={!newFolderName.trim()}
                className="px-4 py-2 bg-gradient-to-r from-amber-400 to-pink-400 text-white rounded-lg hover:from-rose-300 hover:to-amber-300 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
              >
                Create Folder
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default IDEPage;
