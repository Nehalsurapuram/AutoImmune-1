import React, { useMemo } from 'react';

interface DiffViewerProps {
  diffText?: string | null;
  filePath?: string | null;
  className?: string;
}

function truncateMiddle(str: string, maxLen: number = 36): string {
  if (!str || str.length <= maxLen) return str;
  const charsToShow = maxLen - 3;
  const frontChars = Math.ceil(charsToShow / 2);
  const backChars = Math.floor(charsToShow / 2);
  return str.slice(0, frontChars) + '...' + str.slice(str.length - backChars);
}

export const DiffViewer: React.FC<DiffViewerProps> = ({
  diffText,
  filePath,
  className = '',
}) => {
  const lines = useMemo(() => {
    if (!diffText) return [];
    return diffText.split('\n');
  }, [diffText]);

  if (!diffText || lines.length === 0) {
    return (
      <div className={`p-6 bg-surface rounded border border-line text-sm text-text-3 ${className}`}>
        No candidate diff available for this record.
      </div>
    );
  }

  const displayPath = filePath ? truncateMiddle(filePath, 36) : '';

  return (
    <div className={`border border-line rounded overflow-hidden bg-surface text-sm ${className}`}>
      {filePath && (
        <div className="bg-surface-2 px-4 py-2 border-b border-line text-text font-medium flex items-center justify-between text-sm gap-3">
          <span className="truncate min-w-0" title={filePath}>
            <code>{displayPath}</code>
          </span>
          <span className="text-sm text-text-3 tabular-nums font-normal whitespace-nowrap flex-shrink-0">
            {lines.length} lines
          </span>
        </div>
      )}
      <div className="overflow-x-auto max-h-[520px] p-2 leading-relaxed">
        <table className="w-full border-collapse text-sm">
          <tbody>
            {lines.map((line, idx) => {
              const isHunk = line.startsWith('@@');
              const isAdd = line.startsWith('+') && !line.startsWith('+++');
              const isDel = line.startsWith('-') && !line.startsWith('---');
              const isHeader = line.startsWith('diff') || line.startsWith('index') || line.startsWith('---') || line.startsWith('+++');

              let rowClass = 'hover:bg-surface-2/60';
              let lineNumClass = 'text-text-3';
              let contentClass = 'text-text';

              if (isHunk) {
                rowClass = 'bg-surface-2/90 text-lead-ink font-medium';
                contentClass = 'text-lead-ink font-semibold';
              } else if (isAdd) {
                rowClass = 'bg-success-tint/60 text-success-ink';
                contentClass = 'text-success-ink font-medium';
                lineNumClass = 'text-success-ink';
              } else if (isDel) {
                rowClass = 'bg-danger-tint/60 text-danger-ink';
                contentClass = 'text-danger-ink font-medium';
                lineNumClass = 'text-danger-ink';
              } else if (isHeader) {
                rowClass = 'text-text-3';
                contentClass = 'text-text-3';
              }

              return (
                <tr key={idx} className={`${rowClass} transition-colors`}>
                  <td className={`w-12 select-none pr-3 text-right text-[13px] tabular-nums diff-lineno ${lineNumClass}`}>
                    {idx + 1}
                  </td>
                  <td className="w-5 select-none text-center font-bold text-sm">
                    {isAdd ? '+' : isDel ? '-' : isHunk ? '@' : ' '}
                  </td>
                  <td className={`pl-2 whitespace-pre text-sm ${contentClass}`}>
                    <code>{isAdd || isDel ? line.slice(1) : line}</code>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};
