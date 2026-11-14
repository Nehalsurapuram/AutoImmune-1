import React from 'react';
import { SourceArtifact } from '../../types/evidence';
import { formatTimestamp } from './format';

/** Where every number on the page came from: the analysis file, its hash, the command and the inputs. */
export const Provenance: React.FC<{
  source: string;
  sha?: string;
  generator?: string;
  timestamp?: string;
  methodsDoc?: string;
  artifacts?: SourceArtifact[];
}> = ({ source, sha, generator, timestamp, methodsDoc, artifacts }) => (
  <details className="text-sm text-text-3">
    <summary className="cursor-pointer select-none hover:text-text-2 rounded w-fit min-h-[28px] py-1 leading-5">
      Source <code className="text-text-2">{source}</code>
      {sha && <> · sha256 <code className="text-text-2">{sha}</code></>} · generated {formatTimestamp(timestamp)}
    </summary>
    <div className="mt-2 pl-4 flex flex-col gap-1">
      {generator && (
        <p>
          Regenerate with <code className="text-text-2">{generator}</code>, then <code className="text-text-2">python tools/export_ui_data.py</code>.
        </p>
      )}
      {methodsDoc && (
        <p>
          Method write-up: <code className="text-text-2">{methodsDoc}</code>
        </p>
      )}
      {artifacts && artifacts.length > 0 && (
        <ul className="flex flex-col gap-0.5">
          {artifacts.map((a) => (
            <li key={a.path}>
              <code className="text-text-2">{a.path}</code> {a.sha256_12 && <span className="tabular-nums">· {a.sha256_12}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  </details>
);

/** Shown when the analysis output is missing from the snapshot: say what failed and how to fix it. */
export const ExtensionUnavailable: React.FC<{ title: string; reason?: string }> = ({ title, reason }) => (
  <div className="flex-1 px-8 py-12 max-w-3xl">
    <h1 className="text-[28px] font-bold tracking-tight">{title}</h1>
    <p className="mt-4 text-base text-text">These results are not in the current evidence snapshot.</p>
    <p className="mt-2 text-sm text-text-2">{reason ?? 'No reason was recorded by the exporter.'}</p>
    <p className="mt-2 text-sm text-text-2">
      After regenerating, run <code>python tools/export_ui_data.py</code> and reload this page.
    </p>
  </div>
);
