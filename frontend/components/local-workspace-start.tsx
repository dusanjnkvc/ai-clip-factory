"use client";

import { useState } from "react";

export default function LocalWorkspaceStart() {
  const [showHelp, setShowHelp] = useState(false);
  return (
    <section className="panel form-body local-workspace-start">
      <h2>Automatic AI clipping</h2>
      <p>Free local AI finds highlights and creates editable clips using your computer. Start the local app before opening its workspace.</p>
      <ol>
        <li>Open your <strong>AI Clip Factory</strong> project folder on Windows.</li>
        <li>Double-click <strong>Start ClipFactory.cmd</strong>. It starts the services and opens the workspace when ready.</li>
        <li>Next time you restart your computer, run the launcher again. Use <strong>Stop ClipFactory.cmd</strong> when finished.</li>
      </ol>
      <div className="button-row">
        <a className="button primary" href="http://localhost:3000/" target="_blank" rel="noreferrer">Open running workspace</a>
        <button className="button secondary" type="button" aria-expanded={showHelp} onClick={() => setShowHelp(!showHelp)}>Can’t connect?</button>
      </div>
      <p>The online page can’t start programs on your computer. No paid API key or subscription is needed. Advanced Manual Mode works here in your browser.</p>
      {showHelp && <div className="local-start-help" role="region" aria-label="Local workspace connection help">
        <h3>If localhost refuses to connect</h3>
        <p>Run <strong>Start ClipFactory.cmd</strong> and wait for “ClipFactory is ready”. If startup fails, the launcher keeps its error visible. Details are saved in the project’s <strong>.runtime/local-workspace-error.log</strong>.</p>
        <p>For a new installation, follow the <a href="https://github.com/dusanjnkvc/ai-clip-factory#start-the-local-ai-workspace" target="_blank" rel="noreferrer">free local setup guide</a>. If you already have an older copy, update it from GitHub to get the launcher.</p>
      </div>}
    </section>
  );
}
