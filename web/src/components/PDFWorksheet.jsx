import { useEffect, useRef, useState } from 'react';
import * as pdfjsLib from 'pdfjs-dist';
import LoadingLogo from './LoadingLogo';
import { getWorksheetFields, saveWorksheetAnswers } from '../lib/api';

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
  const saveTimeoutRef = useRef(null);

  // Load PDF
  useEffect(() => {
    console.log('[PDFWorksheet] worksheetUrl:', worksheetUrl);
    console.log('[PDFWorksheet] projectId:', projectId);

    const loadPDF = async () => {
      try {
        setLoading(true);
        console.log('[PDFWorksheet] Starting PDF load...');
        const loadingTask = pdfjsLib.getDocument(worksheetUrl);
        const pdfDoc = await loadingTask.promise;
        console.log('[PDFWorksheet] PDF loaded successfully, pages:', pdfDoc.numPages);
        setPdf(pdfDoc);
        setLoading(false);
      } catch (error) {
        console.error('[PDFWorksheet] Failed to load PDF:', error);
        setLoading(false);
      }
    };

    if (worksheetUrl) {
      loadPDF();
    } else {
      console.log('[PDFWorksheet] No worksheetUrl provided');
    }
  }, [worksheetUrl]);

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

        const data = await getWorksheetFields(projectId);
        console.log('[PDFWorksheet] Received fields:', data.fields?.length || 0);
        console.log('[PDFWorksheet] Received answers:', Object.keys(data.answers || {}).length);

        setFields(data.fields || []);
        setAnswers(data.answers || {});
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
    if (!pdf || !canvasRef.current) return;

    const renderPage = async () => {
      try {
        setRendering(true);
        const page = await pdf.getPage(currentPage);

        // Get the page rotation from PDF metadata
        const pageRotation = page.rotate || 0;
        console.log('[PDFWorksheet] Page rotation detected:', pageRotation);

        // Correct upside-down PDFs (180° rotation)
        // If rotation is 180, we need to rotate it back to 0 to display upright
        // For other rotations (90, 270), respect the original rotation
        let correctedRotation = pageRotation;
        if (pageRotation === 180) {
          correctedRotation = 0; // Flip upside-down PDFs to upright
          console.log('[PDFWorksheet] Correcting upside-down PDF from 180° to 0°');
        }

        const viewport = page.getViewport({ scale, rotation: correctedRotation });

        const canvas = canvasRef.current;
        const context = canvas.getContext('2d');
        canvas.height = viewport.height;
        canvas.width = viewport.width;

        const renderContext = {
          canvasContext: context,
          viewport: viewport
        };

        await page.render(renderContext).promise;
        setRendering(false);
      } catch (error) {
        console.error('Failed to render page:', error);
        setRendering(false);
      }
    };

    renderPage();
  }, [pdf, currentPage, scale]);

  const handleFieldInput = (fieldId, value) => {
    setAnswers(prev => ({ ...prev, [fieldId]: value }));
    onFieldChange?.(fieldId, value);

    // Auto-save with debounce (save 1 second after user stops typing)
    if (saveTimeoutRef.current) {
      clearTimeout(saveTimeoutRef.current);
    }

    saveTimeoutRef.current = setTimeout(async () => {
      try {
        console.log('[PDFWorksheet] Auto-saving answers...');
        const updatedAnswers = { ...answers, [fieldId]: value };
        await saveWorksheetAnswers(projectId, updatedAnswers);
        console.log('[PDFWorksheet] Auto-save complete');
      } catch (error) {
        console.error('[PDFWorksheet] Auto-save failed:', error);
      }
    }, 1000);
  };

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current);
      }
    };
  }, []);

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
      {/* PDF Canvas Container */}
      <div className="relative flex-1 overflow-auto bg-zinc-950/50 p-4">
        {rendering && (
          <div className="absolute inset-0 bg-black/50 flex items-center justify-center z-10">
            <LoadingLogo size="md" />
          </div>
        )}

        <canvas
          ref={canvasRef}
          className="block mx-auto shadow-2xl bg-white"
        />

        {/* Loading fields indicator */}
        {loadingFields && (
          <div className="absolute inset-0 bg-black/30 flex items-center justify-center z-20">
            <div className="bg-zinc-900 px-4 py-2 rounded-lg border border-zinc-700 flex items-center gap-2">
              <LoadingLogo size="sm" />
              <span className="text-sm text-zinc-300">Detecting fillable fields...</span>
            </div>
          </div>
        )}

        {/* Interactive Overlay Layer */}
        {!loadingFields && fields.length > 0 && (() => {
          // Filter fields for current page only
          const pageFields = fields.filter(f => f.page === currentPage);

          return pageFields.length > 0 ? (
            <>
              {/* SVG Highlight Layer */}
              <svg
                className="absolute top-4 left-1/2 -translate-x-1/2 pointer-events-none"
                style={{
                  width: canvasRef.current?.width,
                  height: canvasRef.current?.height
                }}
              >
                {pageFields.map(field => (
                  <rect
                    key={field.id}
                    x={field.bounds.x * scale}
                    y={field.bounds.y * scale}
                    width={field.bounds.width * scale}
                    height={field.bounds.height * scale}
                    className="fill-amber-400/10 stroke-amber-500 stroke-1"
                  />
                ))}
              </svg>

              {/* HTML Input Fields */}
              <div
                className="absolute top-4 left-1/2 -translate-x-1/2"
                style={{
                  width: canvasRef.current?.width,
                  height: canvasRef.current?.height
                }}
              >
                {pageFields.map(field => (
                  <div
                    key={field.id}
                    style={{
                      position: 'absolute',
                      left: field.bounds.x * scale,
                      top: field.bounds.y * scale,
                      width: field.bounds.width * scale,
                      height: field.bounds.height * scale
                    }}
                    className="pointer-events-auto group"
                  >
                    {field.type === 'text_line' && (
                      <input
                        type="text"
                        value={answers[field.id] || ''}
                        onChange={(e) => handleFieldInput(field.id, e.target.value)}
                        className="w-full h-full px-2 bg-white/80 border-2 border-transparent focus:border-amber-500 focus:bg-white rounded outline-none text-sm text-black"
                        placeholder={field.placeholder || ''}
                      />
                    )}

                    {(field.type === 'text_box' || field.type === 'math_work') && (
                      <textarea
                        value={answers[field.id] || ''}
                        onChange={(e) => handleFieldInput(field.id, e.target.value)}
                        className="w-full h-full p-2 bg-white/80 border-2 border-transparent focus:border-amber-500 focus:bg-white rounded outline-none resize-none text-sm text-black"
                        placeholder={field.placeholder || ''}
                      />
                    )}

                    {/* AI Help Button - shows on hover */}
                    <button
                      onClick={() => {/* TODO: Request AI help */}}
                      className="absolute -top-6 right-0 opacity-0 group-hover:opacity-100 bg-gradient-to-r from-amber-500 to-pink-500 text-white px-2 py-1 rounded text-xs shadow-lg transition-opacity cursor-pointer"
                      title="Get AI help with this question"
                    >
                      ✨ Help
                    </button>
                  </div>
                ))}
              </div>
            </>
          ) : null;
        })()}
      </div>

      {/* Page Navigation & Controls */}
      <div className="bg-zinc-950 border-t border-zinc-800 px-4 py-3 flex items-center justify-between">
        {/* Page Navigation */}
        <div className="flex items-center gap-3">
          <button
            onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
            disabled={currentPage === 1}
            className="text-zinc-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition-colors px-3 py-1 rounded hover:bg-zinc-800"
          >
            ← Prev
          </button>
          <span className="text-sm text-zinc-300 min-w-[100px] text-center">
            Page {currentPage} of {pdf?.numPages || 1}
          </span>
          <button
            onClick={() => setCurrentPage(p => Math.min(pdf?.numPages || 1, p + 1))}
            disabled={currentPage === (pdf?.numPages || 1)}
            className="text-zinc-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition-colors px-3 py-1 rounded hover:bg-zinc-800"
          >
            Next →
          </button>
        </div>

        {/* Zoom Controls */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => setScale(s => Math.max(0.5, s - 0.25))}
            className="text-zinc-400 hover:text-white transition-colors w-8 h-8 rounded hover:bg-zinc-800 flex items-center justify-center"
            title="Zoom out"
          >
            −
          </button>
          <span className="text-xs text-zinc-500 min-w-[50px] text-center">
            {Math.round(scale * 100)}%
          </span>
          <button
            onClick={() => setScale(s => Math.min(3, s + 0.25))}
            className="text-zinc-400 hover:text-white transition-colors w-8 h-8 rounded hover:bg-zinc-800 flex items-center justify-center"
            title="Zoom in"
          >
            +
          </button>
        </div>

        {/* Field Count Info */}
        {fields.length > 0 && (
          <div className="text-xs text-zinc-500">
            {Object.keys(answers).length} / {fields.length} fields filled
          </div>
        )}
      </div>
    </div>
  );
}
