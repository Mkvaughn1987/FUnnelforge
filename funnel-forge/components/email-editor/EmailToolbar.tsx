"use client";

interface Props {
  editorRef: React.RefObject<HTMLDivElement | null>;
}

export default function EmailToolbar({ editorRef }: Props) {
  const exec = (cmd: string, val?: string) => {
    document.execCommand(cmd, false, val);
    editorRef.current?.focus();
  };

  const toolbarBtn = "w-8 h-8 flex items-center justify-center rounded hover:bg-surface-hover text-text-secondary hover:text-accent-blue transition-colors";
  const divider = "w-px h-5 bg-border mx-1.5";

  return (
    <div className="flex items-center gap-0.5 px-4 py-2 border-b border-border bg-bg/30 flex-wrap">
      {/* Font size */}
      <select
        onChange={(e) => { exec("fontSize", e.target.value); e.target.value = ""; }}
        defaultValue=""
        className="h-8 px-2 rounded bg-surface border border-border text-text-primary text-xs focus:outline-none focus:border-accent-blue mr-1"
      >
        <option value="" disabled>Font Size</option>
        <option value="1">8</option>
        <option value="2">10</option>
        <option value="3">12</option>
        <option value="4">14</option>
        <option value="5">18</option>
        <option value="6">24</option>
        <option value="7">36</option>
      </select>

      <div className={divider} />

      {/* Text style */}
      <button onMouseDown={(e) => { e.preventDefault(); exec("bold"); }} className={toolbarBtn} title="Bold">
        <span className="text-sm font-bold">B</span>
      </button>
      <button onMouseDown={(e) => { e.preventDefault(); exec("italic"); }} className={toolbarBtn} title="Italic">
        <span className="text-sm italic font-serif">I</span>
      </button>
      <button onMouseDown={(e) => { e.preventDefault(); exec("underline"); }} className={toolbarBtn} title="Underline">
        <span className="text-sm underline">U</span>
      </button>

      <div className={divider} />

      {/* Alignment */}
      <button onMouseDown={(e) => { e.preventDefault(); exec("justifyLeft"); }} className={toolbarBtn} title="Align Left">
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" d="M3 6h18M3 12h12M3 18h18" />
        </svg>
      </button>
      <button onMouseDown={(e) => { e.preventDefault(); exec("justifyCenter"); }} className={toolbarBtn} title="Align Center">
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" d="M3 6h18M6 12h12M3 18h18" />
        </svg>
      </button>
      <button onMouseDown={(e) => { e.preventDefault(); exec("justifyRight"); }} className={toolbarBtn} title="Align Right">
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" d="M3 6h18M9 12h12M3 18h18" />
        </svg>
      </button>

      <div className={divider} />

      {/* Lists */}
      <button onMouseDown={(e) => { e.preventDefault(); exec("insertUnorderedList"); }} className={toolbarBtn} title="Bullet List">
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" d="M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01" />
        </svg>
      </button>
      <button onMouseDown={(e) => { e.preventDefault(); exec("insertOrderedList"); }} className={toolbarBtn} title="Numbered List">
        <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" d="M10 6h11M10 12h11M10 18h11" />
          <text x="2" y="8" fill="currentColor" stroke="none" fontSize="7" fontFamily="sans-serif" fontWeight="600">1</text>
          <text x="2" y="14" fill="currentColor" stroke="none" fontSize="7" fontFamily="sans-serif" fontWeight="600">2</text>
          <text x="2" y="20" fill="currentColor" stroke="none" fontSize="7" fontFamily="sans-serif" fontWeight="600">3</text>
        </svg>
      </button>

      <div className={divider} />

      {/* Link */}
      <button
        onMouseDown={(e) => {
          e.preventDefault();
          const url = prompt("Enter URL:");
          if (url) exec("createLink", url);
        }}
        className={toolbarBtn}
        title="Insert Link"
      >
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M13.19 8.688a4.5 4.5 0 0 1 1.242 7.244l-4.5 4.5a4.5 4.5 0 0 1-6.364-6.364l1.757-1.757m13.35-.622 1.757-1.757a4.5 4.5 0 0 0-6.364-6.364l-4.5 4.5a4.5 4.5 0 0 0 1.242 7.244" />
        </svg>
      </button>
    </div>
  );
}
