import { useEffect, useRef, useState, useCallback } from 'react';
import * as pdfjsLib from 'pdfjs-dist';
import LoadingLogo from './LoadingLogo';
import { getWorksheetFields, saveWorksheetAnswers, getWorksheetFieldSuggestion } from '../lib/api';
import { getAuthHeader } from '../lib/auth';

// Set up PDF.js worker - use the version from node_modules via Vite
// Vite will automatically handle this import
import pdfjsWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
pdfjsLib.GlobalWorkerOptions.workerSrc = pdfjsWorker;

export default function PDFWorksheet({
  worksheetUrl,
  projectId,
  onFieldChange
}) {
  const canvasRef = useRef(null);
  const containerRef = useRef(null);
  const [pdf, setPdf] = useState(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [fields, setFields] = useState([]);
  const [answers, setAnswers] = useState({});
  const [scale, setScale] = useState(1.5);
  const [loading, setLoading] = useState(true);
  const [rendering, setRendering] = useState(false);
  const [loadingFields, setLoadingFields] = useState(true);
  const renderTaskRef = useRef(null);
  const viewportRef = useRef(null);
  const cssDimensionsRef = useRef({ width: 0, height: 0 });
  const pdfDimensionsRef = useRef({});
  const [pageDimensions, setPageDimensions] = useState({ width: 0, height: 0 });
  const hasManualScaleRef = useRef(false);
  const saveTimeoutRef = useRef(null);
  const autoSaveIntervalRef = useRef(null);
  const latestAnswersRef = useRef({});
  const lastSavedAnswersRef = useRef({});
  const [fieldSuggestions, setFieldSuggestions] = useState({});
  const [activeSuggestionField, setActiveSuggestionField] = useState(null);
  const [helpLoadingField, setHelpLoadingField] = useState(null);
  const [helpError, setHelpError] = useState(null);
  const [saveStatus, setSaveStatus] = useState('saved'); // 'saved', 'saving', 'error'
  const [isSaving, setIsSaving] = useState(false);

  const computeFitScale = useCallback(
    async (pageNumber = 1, attempt = 0) => {
      if (!pdf || hasManualScaleRef.current) {
        return;
      }

      const container = containerRef.current;
      if (!container) {
        return;
      }

      const containerWidth = container.clientWidth;
      if (!containerWidth) {
        if (attempt < 5) {
          setTimeout(() => computeFitScale(pageNumber, attempt + 1), 120);
        }
        return;
      }

      try {
        const page = await pdf.getPage(pageNumber);
        let pageRotation = page.rotate || 0;
        pageRotation = ((pageRotation % 360) + 360) % 360;
        if (pageRotation === 180) {
          pageRotation = 0;
        }

        const viewport = page.getViewport({ scale: 1, rotation: pageRotation });
        const horizontalPadding = 64; // account for container padding and gutters
        const availableWidth = containerWidth - horizontalPadding;
        if (!viewport.width || availableWidth <= 0) {
          if (attempt < 5) {
            setTimeout(() => computeFitScale(pageNumber, attempt + 1), 120);
          }
          return;
        }

        const targetScale = availableWidth / viewport.width;
        const clampedScale = Math.max(0.5, Math.min(3, targetScale));
        setScale((prev) => (Math.abs(prev - clampedScale) < 0.01 ? prev : clampedScale));
      } catch (error) {
        console.warn('[PDFWorksheet] Failed to compute fit scale:', error);
      }
    },
    [pdf]
  );

  // Load PDF
  useEffect(() => {
    console.log('[PDFWorksheet] worksheetUrl:', worksheetUrl);
    console.log('[PDFWorksheet] projectId:', projectId);

    if (!worksheetUrl) {
      console.log('[PDFWorksheet] No worksheetUrl provided');
      setPdf(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    const loadingTask = pdfjsLib.getDocument(worksheetUrl);

    const loadPDF = async () => {
      try {
        console.log('[PDFWorksheet] Starting PDF load...');
        const pdfDoc = await loadingTask.promise;
        if (cancelled) {
          await pdfDoc.destroy?.();
          return;
        }
        console.log('[PDFWorksheet] PDF loaded successfully, pages:', pdfDoc.numPages);
        setPdf(pdfDoc);
      } catch (error) {
        if (!cancelled) {
          console.error('[PDFWorksheet] Failed to load PDF:', error);
          setPdf(null);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    loadPDF();

    return () => {
      cancelled = true;
      setPdf(null);
      setPageDimensions({ width: 0, height: 0 });
      try {
        loadingTask.destroy();
      } catch (cleanupError) {
        console.warn('[PDFWorksheet] Failed to clean up loading task:', cleanupError);
      }
    };
  }, [worksheetUrl]);

  useEffect(() => {
    if (!pdf) {
      return;
    }
    setCurrentPage(1);
    setPageDimensions({ width: 0, height: 0 });
    hasManualScaleRef.current = false;
  }, [pdf]);

  useEffect(() => {
    if (!pdf || hasManualScaleRef.current) {
      return;
    }
    computeFitScale(currentPage);
  }, [pdf, currentPage, computeFitScale]);

  useEffect(() => {
    if (!pdf || typeof ResizeObserver === 'undefined') {
      return;
    }
    const container = containerRef.current;
    if (!container) {
      return;
    }

    const observer = new ResizeObserver(() => {
      if (hasManualScaleRef.current) {
        return;
      }
      computeFitScale(currentPage);
    });

    observer.observe(container);

    return () => {
      observer.disconnect();
    };
  }, [pdf, computeFitScale, currentPage]);

// Fetch detected fields and saved answers from backend
  useEffect(() => {
    if (!projectId) {
      setLoadingFields(false);
      return;
    }

    const fetchFields = async () => {
      try {
        setLoadingFields(true);
        console.log('[PDFWorksheet] Fetching worksheet fields for project:', projectId);

        const data = await getWorksheetFields(projectId, getAuthHeader());
        console.log('[PDFWorksheet] Received fields:', data.fields?.length || 0);
        console.log('[PDFWorksheet] Received answers:', Object.keys(data.answers || {}).length);

        const initialAnswers = data.answers || {};
        setFields(data.fields || []);
        setAnswers(initialAnswers);
        latestAnswersRef.current = initialAnswers;
        lastSavedAnswersRef.current = initialAnswers;
        pdfDimensionsRef.current = data.page_dimensions || {};
        setFieldSuggestions({});
        setActiveSuggestionField(null);
        setHelpError(null);
        setSaveStatus('saved');
        setLoadingFields(false);
      } catch (error) {
        console.error('[PDFWorksheet] Failed to fetch fields:', error);
        // Not a critical error - worksheet can still be viewed
        setLoadingFields(false);
      }
    };

    fetchFields();
  }, [projectId]);

  // Render current page
  useEffect(() => {
    if (!pdf || !canvasRef.current) {
      return;
    }

    let cancelled = false;

    const renderPage = async () => {
      try {
        setRendering(true);
        const page = await pdf.getPage(currentPage);

        let pageRotation = page.rotate || 0;
        pageRotation = ((pageRotation % 360) + 360) % 360;
        if (pageRotation === 180) {
          console.log('[PDFWorksheet] Correcting upside-down PDF from 180deg to 0deg');
          pageRotation = 0;
        }

        const viewport = page.getViewport({ scale, rotation: pageRotation });
        viewportRef.current = viewport;

        const pageView = page.view;
        if (Array.isArray(pageView) && pageView.length === 4) {
          const [xMin, yMin, xMax, yMax] = pageView;
          const pdfWidth = Math.abs((xMax ?? 0) - (xMin ?? 0));
          const pdfHeight = Math.abs((yMax ?? 0) - (yMin ?? 0));
          if (pdfWidth > 0 && pdfHeight > 0) {
            // Snapshot the canonical PDF user-space dimensions so overlays track the exact viewport geometry.
            pdfDimensionsRef.current[String(currentPage)] = {
              width: pdfWidth,
              height: pdfHeight,
              xMin,
              yMin
            };
          }
        }
        const canvas = canvasRef.current;
        const context = canvas.getContext('2d');
        if (!context) {
          return;
        }

        const outputScale = window.devicePixelRatio || 1;
        const displayWidth = viewport.width;
        const displayHeight = viewport.height;
        cssDimensionsRef.current = { width: displayWidth, height: displayHeight };

        canvas.style.width = `${displayWidth}px`;
        canvas.style.height = `${displayHeight}px`;
        canvas.width = Math.floor(displayWidth * outputScale);
        canvas.height = Math.floor(displayHeight * outputScale);

        context.setTransform(outputScale, 0, 0, outputScale, 0, 0);
        context.clearRect(0, 0, canvas.width, canvas.height);

        const updateMeasuredDimensions = () => {
          const rect = canvas.getBoundingClientRect();
          if (!rect?.width || !rect?.height) {
            return;
          }
          cssDimensionsRef.current = { width: rect.width, height: rect.height };
          setPageDimensions((prev) =>
            Math.abs(prev.width - rect.width) < 0.5 && Math.abs(prev.height - rect.height) < 0.5
              ? prev
              : { width: rect.width, height: rect.height }
          );
        };

        updateMeasuredDimensions();
        requestAnimationFrame(updateMeasuredDimensions);

        if (renderTaskRef.current) {
          try {
            renderTaskRef.current.cancel();
          } catch (cancelError) {
            console.warn('[PDFWorksheet] Failed to cancel existing render task:', cancelError);
          }
        }

        const renderContext = { canvasContext: context, viewport };
        const renderTask = page.render(renderContext);
        renderTaskRef.current = renderTask;

        await renderTask.promise;
        if (!cancelled) {
          setRendering(false);
        }
      } catch (error) {
        if (error?.name === 'RenderingCancelledException') {
          console.log('[PDFWorksheet] Render cancelled');
        } else {
          console.error('Failed to render page:', error);
        }
        if (!cancelled) {
          setRendering(false);
        }
      } finally {
        if (!cancelled) {
          renderTaskRef.current = null;
        }
      }
    };

    renderPage();

    return () => {
      cancelled = true;
      viewportRef.current = null;
      if (renderTaskRef.current) {
        try {
          renderTaskRef.current.cancel();
        } catch (cancelError) {
          console.warn('[PDFWorksheet] Error cancelling render task during cleanup:', cancelError);
        }
        renderTaskRef.current = null;
      }
    };
  }, [pdf, currentPage, scale]);

  // Helper function to save answers to Supabase
  const performSave = useCallback(async (retryCount = 0) => {
    if (!projectId || isSaving) return;

    // Check if there are changes to save
    const hasChanges = JSON.stringify(latestAnswersRef.current) !== JSON.stringify(lastSavedAnswersRef.current);
    if (!hasChanges) {
      // No changes, ensure status shows saved
      if (saveStatus !== 'saved') {
        setSaveStatus('saved');
      }
      return;
    }

    try {
      setIsSaving(true);
      setSaveStatus('saving');
      console.log('[PDFWorksheet] Auto-saving answers...');

      await saveWorksheetAnswers(projectId, latestAnswersRef.current, getAuthHeader());

      lastSavedAnswersRef.current = { ...latestAnswersRef.current };
      setSaveStatus('saved');
      setIsSaving(false);
      console.log('[PDFWorksheet] Auto-save complete');
    } catch (error) {
      console.error('[PDFWorksheet] Auto-save failed:', error);

      // Retry up to 2 times with exponential backoff
      if (retryCount < 2) {
        console.log(`[PDFWorksheet] Retrying save (attempt ${retryCount + 1}/2)...`);
        // Don't clear isSaving flag yet - keep it locked during retry
        setTimeout(() => {
          setIsSaving(false); // Clear flag before retry
          performSave(retryCount + 1);
        }, 1000 * Math.pow(2, retryCount)); // 1s, 2s backoff
      } else {
        setSaveStatus('error');
        setIsSaving(false);
      }
    }
  }, [projectId, isSaving, saveStatus]);

  const handleFieldInput = (fieldId, value) => {
    setAnswers(prev => {
      const next = { ...prev, [fieldId]: value };
      latestAnswersRef.current = next;
      return next;
    });
    onFieldChange?.(fieldId, value);
    setSaveStatus('unsaved');

    // Debounced save (save 1 second after user stops typing)
    if (saveTimeoutRef.current) {
      clearTimeout(saveTimeoutRef.current);
    }

    saveTimeoutRef.current = setTimeout(() => {
      performSave();
    }, 1000);
  };

  const requestFieldHelp = async (field) => {
    if (!projectId) {
      return;
    }
    setHelpError(null);
    setActiveSuggestionField(field.id);
    setHelpLoadingField(field.id);
    try {
      const suggestion = await getWorksheetFieldSuggestion(
        projectId,
        field.id,
        {
          current_answer: latestAnswersRef.current[field.id] || '',
        },
        getAuthHeader()
      );
      setFieldSuggestions(prev => ({ ...prev, [field.id]: suggestion }));
    } catch (error) {
      console.error('[PDFWorksheet] AI help failed:', error);
      setHelpError({
        fieldId: field.id,
        message: error?.message || 'Unable to fetch AI help right now.',
      });
    } finally {
      setHelpLoadingField(null);
    }
  };

  const applySuggestion = (fieldId) => {
    const suggestion = fieldSuggestions[fieldId];
    if (!suggestion?.suggestion) {
      return;
    }
    handleFieldInput(fieldId, suggestion.suggestion);
  };

  // Continuous auto-save interval (every 3 seconds)
  useEffect(() => {
    if (!projectId) return;

    // Set up interval to auto-save every 3 seconds
    autoSaveIntervalRef.current = setInterval(() => {
      performSave();
    }, 3000);

    return () => {
      // Cleanup: clear interval and timeout, perform final save
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current);
      }
      if (autoSaveIntervalRef.current) {
        clearInterval(autoSaveIntervalRef.current);
      }
      // Fire-and-forget final save with latest answers
      if (Object.keys(latestAnswersRef.current || {}).length) {
        saveWorksheetAnswers(projectId, latestAnswersRef.current, getAuthHeader()).catch(err => {
          console.error('[PDFWorksheet] Final save failed during unmount:', err);
        });
      }
    };
  }, [projectId, performSave]);

  const handleZoomOut = useCallback(() => {
    hasManualScaleRef.current = true;
    setScale((prev) => Math.max(0.5, prev - 0.25));
  }, []);

  const handleZoomIn = useCallback(() => {
    hasManualScaleRef.current = true;
    setScale((prev) => Math.min(3, prev + 0.25));
  }, []);

  const handleResetZoom = useCallback(() => {
    hasManualScaleRef.current = false;
    computeFitScale(currentPage);
  }, [computeFitScale, currentPage]);

  const hasPageDimensions = pageDimensions.width > 0 && pageDimensions.height > 0;

  const getViewportRect = (bounds = {}, page = currentPage) => {
    const viewport = viewportRef.current;
    const pdfDims = pdfDimensionsRef.current[String(page)] || {};
    const pdfWidth = pdfDims.width || 0;
    const pdfHeight = pdfDims.height || 0;
    const cssDims = cssDimensionsRef.current;
    const cssWidth = cssDims.width || pageDimensions.width || 0;
    const cssHeight = cssDims.height || pageDimensions.height || 0;

    if (!bounds || (!pdfWidth && !cssWidth) || (!pdfHeight && !cssHeight)) {
      return { left: 0, top: 0, width: 0, height: 0 };
    }

    const rawX = Number(bounds.x) || 0;
    const rawY = Number(bounds.y) || 0;
    const rawW = Number(bounds.width) || 0;
    const rawH = Number(bounds.height) || 0;

    const usesNormalized = rawX <= 1 && rawY <= 1 && rawW <= 1 && rawH <= 1;

    console.log('[PDFWorksheet] getViewportRect - bounds:', bounds, 'usesNormalized:', usesNormalized);
    console.log('[PDFWorksheet] getViewportRect - cssWidth:', cssWidth, 'cssHeight:', cssHeight);
    console.log('[PDFWorksheet] getViewportRect - pdfWidth:', pdfWidth, 'pdfHeight:', pdfHeight);

    if (!usesNormalized) {
      console.error('[PDFWorksheet] Received non-normalized coordinates - this should not happen with bounds_version >= 3');
      return { left: 0, top: 0, width: 0, height: 0 };
    }

    // Coordinates are normalized (0-1 range) with top-left origin
    // Apply 5/3 DPI scale factor (120 DPI / 72 DPI)
    const SCALE_FACTOR = 5 / 3;

    const left = rawX * cssWidth * SCALE_FACTOR;
    const top = rawY * cssHeight * SCALE_FACTOR;
    const width = rawW * cssWidth * SCALE_FACTOR;
    const height = rawH * cssHeight * SCALE_FACTOR;

    console.log('[PDFWorksheet] getViewportRect - result:', { left, top, width, height });

    return { left, top, width, height };
  };

if (loading) {
    return (
      <div className="flex items-center justify-center h-96 bg-zinc-950 rounded-lg border border-zinc-800">
        <div className="text-center">
          <LoadingLogo size="lg" />
          <p className="text-zinc-400 mt-4">Loading worksheet...</p>
        </div>
      </div>
    );
  }

  if (!pdf) {
    return (
      <div className="flex items-center justify-center h-96 bg-zinc-950 rounded-lg border border-zinc-800">
        <div className="text-center px-6">
          <svg className="w-16 h-16 mx-auto mb-4 text-zinc-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
          </svg>
          <p className="text-zinc-400 mb-2">No worksheet loaded</p>
          <p className="text-xs text-zinc-600">The PDF worksheet is only available during this session.</p>
          <p className="text-xs text-zinc-600 mt-1">To reload it, please upload the PDF file again.</p>
        </div>
      </div>
    );
  }

  return (
    <div ref={containerRef} className="flex flex-col h-full bg-zinc-900 rounded-lg overflow-hidden border border-zinc-800">
      {/* AI Help Loading Indicator */}
      {helpLoadingField && (
        <div className="absolute top-4 left-4 z-30">
          <div className="flex items-center gap-2 px-3 py-1.5 bg-purple-950/90 border border-purple-800/50 rounded-lg backdrop-blur-sm animate-in fade-in slide-in-from-top-2">
            <LoadingLogo size="xs" />
            <span className="text-xs text-purple-300">AI thinking...</span>
          </div>
        </div>
      )}

      {/* PDF Canvas Container */}
      <div className="relative flex-1 overflow-auto bg-zinc-950/50 p-4">
        {rendering && (
          <div className="absolute inset-0 bg-black/50 flex items-center justify-center z-10">
            <LoadingLogo size="md" />
          </div>
        )}

        {/* Loading fields indicator */}
        {loadingFields && (
          <div className="absolute inset-0 bg-black/30 flex items-center justify-center z-20">
            <div className="bg-zinc-900 px-4 py-2 rounded-lg border border-zinc-700 flex items-center gap-2">
              <LoadingLogo size="sm" />
              <span className="text-sm text-zinc-300">Detecting fillable fields...</span>
            </div>
          </div>
        )}

        {/* Wrapper to constrain canvas and overlays */}
        <div className="relative inline-block mx-auto">
          <canvas
            ref={canvasRef}
            className="block shadow-2xl bg-white"
          />

          {/* Interactive Overlay Layer */}
          {!loadingFields && fields.length > 0 && hasPageDimensions && (() => {
            // Filter fields for current page only
            const pageFields = fields.filter(f => f.page === currentPage);

            return pageFields.length > 0 ? (
              <>
                {/* SVG Highlight Layer */}
                <svg
                  className="absolute top-0 left-0 pointer-events-none"
                  style={{
                    width: pageDimensions.width,
                    height: pageDimensions.height
                  }}
                >
                {pageFields.map(field => {
                  const rect = getViewportRect(field.bounds, field.page);
                  return (
                    <rect
                      key={field.id}
                      x={rect.left}
                      y={rect.top}
                      width={rect.width}
                      height={rect.height}
                      className="fill-amber-400/10 stroke-amber-500 stroke-1"
                    />
                  );
                })}
              </svg>

              {/* HTML Input Fields */}
              <div
                className="absolute top-0 left-0"
                style={{
                  width: pageDimensions.width,
                  height: pageDimensions.height
                }}
              >
                {pageFields.map(field => {
                  const rect = getViewportRect(field.bounds, field.page);
                  if (
                    import.meta.env?.DEV &&
                    (field.id === 'page1_field0' || field.id === 'page1_field2' || field.id === 'page1_field12')
                  ) {
                    // eslint-disable-next-line no-console
                    console.log('[PDFWorksheet] rect debug', {
                      fieldId: field.id,
                      bounds: field.bounds,
                      rect,
                      page: field.page,
                      pageDims: pdfDimensionsRef.current[String(field.page)] || null,
                      viewportDims: viewportRef.current
                        ? { width: viewportRef.current.width, height: viewportRef.current.height, scale: viewportRef.current.scale }
                        : null
                    });
                  }
                  return (
                    <div
                      key={field.id}
                      style={{
                        position: 'absolute',
                        left: rect.left,
                        top: rect.top,
                        width: rect.width,
                        height: rect.height
                      }}
                      className="pointer-events-auto"
                    >
                      <div className="relative w-full h-full group">
                        {field.type === 'text_line' && (
                          <input
                            type="text"
                            value={answers[field.id] || ''}
                            onChange={(e) => handleFieldInput(field.id, e.target.value)}
                            data-field-id={field.id}
                            className="w-full h-full px-2 bg-white/90 border-2 border-amber-400/30 hover:border-amber-500/50 focus:border-amber-500 focus:bg-white focus:shadow-lg focus:shadow-amber-500/20 rounded outline-none text-sm text-black placeholder-zinc-400 transition-all"
                            placeholder={field.placeholder || 'Type your answer...'}
                            title={field.context || field.placeholder}
                          />
                        )}

                        {(field.type === 'text_box' || field.type === 'math_work') && (
                          <textarea
                            value={answers[field.id] || ''}
                            onChange={(e) => handleFieldInput(field.id, e.target.value)}
                            data-field-id={field.id}
                            className="w-full h-full p-2 bg-white/90 border-2 border-amber-400/30 hover:border-amber-500/50 focus:border-amber-500 focus:bg-white focus:shadow-lg focus:shadow-amber-500/20 rounded outline-none resize-none text-sm text-black placeholder-zinc-400 transition-all"
                            placeholder={field.placeholder || 'Type your work here...'}
                            title={field.context || field.placeholder}
                          />
                        )}

                        {/* AI Help Button - shows on hover or if there's a suggestion */}
                        <button
                          type="button"
                          onClick={() => requestFieldHelp(field)}
                          disabled={helpLoadingField === field.id}
                          className={`absolute top-1/2 -translate-y-1/2 left-full ml-2 bg-gradient-to-r from-amber-500 to-pink-500 text-white px-3 py-1.5 rounded-lg text-xs font-medium shadow-lg transition-all cursor-pointer disabled:opacity-60 disabled:cursor-default flex items-center gap-1.5 ${
                            fieldSuggestions[field.id] || activeSuggestionField === field.id
                              ? 'opacity-100 translate-x-0'
                              : 'opacity-0 -translate-x-2 group-hover:opacity-100 group-hover:translate-x-0'
                          }`}
                          title="Get AI help with this question (Ctrl+Space)"
                        >
                          {helpLoadingField === field.id ? (
                            <>
                              <LoadingLogo size="xs" />
                              <span>Thinking...</span>
                            </>
                          ) : (
                            <>
                              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                              </svg>
                              <span>AI Help</span>
                            </>
                          )}
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </>
          ) : null;
        })()}
        </div>
      </div>

      {/* Page Navigation & Controls */}
      <div className="bg-zinc-950 border-t border-zinc-800 px-4 py-3 flex items-center justify-between">
        {/* Page Navigation */}
        <div className="flex items-center gap-3">
          <button
            onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
            disabled={currentPage === 1}
            className="text-zinc-400 hover:text-white disabled:opacity-30 disabled:cursor-default cursor-pointer transition-colors px-3 py-1 rounded hover:bg-zinc-800 flex items-center gap-1"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
            Prev
          </button>
          <span className="text-sm text-zinc-300 min-w-[100px] text-center">
            Page {currentPage} of {pdf?.numPages || 1}
          </span>
          <button
            onClick={() => setCurrentPage(p => Math.min(pdf?.numPages || 1, p + 1))}
            disabled={currentPage === (pdf?.numPages || 1)}
            className="text-zinc-400 hover:text-white disabled:opacity-30 disabled:cursor-default cursor-pointer transition-colors px-3 py-1 rounded hover:bg-zinc-800 flex items-center gap-1"
          >
            Next
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          </button>
        </div>

        {/* Zoom Controls */}
        <div className="flex items-center gap-2">
          <button
            onClick={handleZoomOut}
            className="text-zinc-400 hover:text-white transition-colors w-8 h-8 rounded hover:bg-zinc-800 flex items-center justify-center cursor-pointer"
            title="Zoom out"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0zM13 10H7" />
            </svg>
          </button>
          <span className="text-sm w-16 text-center">
            {Math.round(scale * 100)}%
          </span>
          <button
            onClick={handleZoomIn}
            className="text-zinc-400 hover:text-white transition-colors w-8 h-8 rounded hover:bg-zinc-800 flex items-center justify-center cursor-pointer"
            title="Zoom in"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0zM10 7v3m0 0v3m0-3h3m-3 0H7" />
            </svg>
          </button>
          <button
            onClick={handleResetZoom}
            className="text-zinc-400 hover:text-white transition-colors px-3 h-8 rounded hover:bg-zinc-800 flex items-center justify-center cursor-pointer"
            title="Fit to screen"
          >
            Fit
          </button>
        </div>

        {/* Field Count Info */}
        {fields.length > 0 && (
          <div className="flex items-center gap-3">
            <div className="text-xs text-zinc-500">
              {Object.values(answers).filter(val => val && val.trim()).length} / {fields.length} fields filled
            </div>
            <div className="h-4 w-px bg-zinc-700"></div>
            <div className="text-xs text-zinc-500 flex items-center gap-1.5">
              <svg className="w-3 h-3 text-amber-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span>Hover fields for AI help</span>
            </div>
          </div>
        )}
      </div>
      {activeSuggestionField && (
        <div className="border-t border-zinc-800 bg-zinc-950/80 px-4 py-4 space-y-3">
          {helpLoadingField === activeSuggestionField ? (
            <div className="flex items-center gap-2 text-sm text-zinc-300">
              <LoadingLogo size="sm" />
              <span>Gathering ideas...</span>
            </div>
          ) : helpError && helpError.fieldId === activeSuggestionField ? (
            <div className="text-sm text-red-400">
              {helpError.message}
            </div>
          ) : fieldSuggestions[activeSuggestionField] ? (
            <div className="space-y-2">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-zinc-100">AI suggestion</p>
                  <p className="text-xs text-zinc-500">
                    Confidence: {fieldSuggestions[activeSuggestionField]?.confidence || 'medium'}
                  </p>
                </div>
                <div className="flex gap-2">
                  <button
                    type="button"
                    className="text-xs px-3 py-1 rounded border border-zinc-700 text-zinc-300 hover:bg-zinc-800 transition-colors cursor-pointer"
                    onClick={() => setActiveSuggestionField(null)}
                  >
                    Dismiss
                  </button>
                  <button
                    type="button"
                    className="text-xs px-3 py-1 rounded bg-gradient-to-r from-amber-400 to-pink-500 text-black font-semibold hover:from-amber-300 hover:to-pink-400 transition-colors cursor-pointer"
                    onClick={() => applySuggestion(activeSuggestionField)}
                  >
                    Apply
                  </button>
                </div>
              </div>
              <p className="text-sm text-zinc-200 whitespace-pre-wrap leading-relaxed">
                {fieldSuggestions[activeSuggestionField]?.suggestion || ''}
              </p>
              {fieldSuggestions[activeSuggestionField]?.explanation && (
                <p className="text-xs text-zinc-500">
                  Why it helps: {fieldSuggestions[activeSuggestionField].explanation}
                </p>
              )}
            </div>
          ) : (
            <div className="text-sm text-zinc-400">
              No suggestion available for this field yet.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
