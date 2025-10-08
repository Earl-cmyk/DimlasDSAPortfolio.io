// static/js/main.js - minimal interactive client
async function api(path, opts){
  const resp = await fetch(path, opts);
  const ct = resp.headers.get("content-type") || "";
  if (ct.includes("application/json")) return resp.json();
  return resp.text();
}

/* Works page logic */
document.addEventListener("DOMContentLoaded", ()=> {
  // if on works page, initialize
  if (document.getElementById("folders-list")) {
    loadFolders();
    loadUploadFolders();
    loadFiles();

    document.getElementById("create-folder").addEventListener("click", async ()=>{
      const name = document.getElementById("new-folder-name").value.trim();
      if (!name) return alert("Enter folder name");
      await fetch("/api/folders", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({name})});
      document.getElementById("new-folder-name").value = "";
      await loadFolders();
      await loadUploadFolders();
    });

    document.getElementById("upload-form").addEventListener("submit", async (e)=>{
      e.preventDefault();
      const fileInput = document.getElementById("file-input");
      if (!fileInput.files.length) { alert("Select a file"); return; }
      const fd = new FormData();
      fd.append("file", fileInput.files[0]);
      const folder = document.getElementById("upload-folder").value;
      if (folder) fd.append("folder_id", folder);
      const res = await fetch("/api/files", {method:"POST", body:fd});
      const data = await res.json();
      if (res.status === 201) {
        alert("Uploaded");
        fileInput.value = "";
        loadFiles();
      } else {
        alert("Upload error: " + (data.error || JSON.stringify(data)));
      }
    });

    // file editor save/run
    window.selectedFileId = null;
    document.getElementById("save-file").addEventListener("click", async ()=>{
      if (!window.selectedFileId) return alert("Pick a file first");
      const content = document.getElementById("file-content").value;
      await fetch(`/api/file-content/${window.selectedFileId}`, {method:"PUT", headers:{"Content-Type":"application/json"}, body:JSON.stringify({content})});
      alert("Saved");
    });
    document.getElementById("run-file").addEventListener("click", async ()=>{
      if (!window.selectedFileId) return alert("Pick a file first");
      const outPre = document.getElementById("run-output");
      outPre.textContent = "Running...";
      const res = await fetch(`/api/exec/${window.selectedFileId}`, {method:"POST"});
      const data = await res.json();
      if (data.error) {
        outPre.textContent = "Error: " + data.error;
      } else {
        outPre.textContent = `Return code: ${data.returncode}\n\nSTDOUT:\n${data.stdout}\n\nSTDERR:\n${data.stderr}`;
      }
    });
  }

  // mini tools
  document.querySelectorAll(".mini-btn").forEach(b=>{
    b.addEventListener("click", ()=>{
      const tool = b.dataset.tool;
      const panel = document.getElementById("tools-panel");
      const content = document.getElementById("tools-content");
      panel.style.display = "block";
      if (tool === "Uppercaser") {
        content.innerHTML = `<h4>Uppercaser</h4>
          <textarea id="uc-text" style="width:100%;height:80px;"></textarea>
          <button id="uc-go">Uppercase</button>
          <pre id="uc-res"></pre>`;
        document.getElementById("uc-go").addEventListener("click", async ()=>{
          const val = document.getElementById("uc-text").value;
          const r = await api("/api/tool/uppercaser", {method:"POST", body:JSON.stringify({text:val}), headers:{"Content-Type":"application/json"}});
          document.getElementById("uc-res").textContent = r.result;
        });
      } else if (tool === "Area of Circle") {
        content.innerHTML = `<h4>Area of Circle</h4>
          <input id="circle-radius" placeholder="radius" />
          <button id="circ-go">Compute</button>
          <div id="circ-res"></div>`;
        document.getElementById("circ-go").addEventListener("click", async ()=>{
          const r = document.getElementById("circle-radius").value;
          const res = await api("/api/tool/area/circle", {method:"POST", body:JSON.stringify({radius:r}), headers:{"Content-Type":"application/json"}});
          document.getElementById("circ-res").textContent = res.area ?? res.error;
        });
      } else if (tool === "Area of Triangle") {
        content.innerHTML = `<h4>Area of Triangle</h4>
          <input id="tri-base" placeholder="base" />
          <input id="tri-height" placeholder="height" />
          <button id="tri-go">Compute</button>
          <div id="tri-res"></div>`;
        document.getElementById("tri-go").addEventListener("click", async ()=>{
          const base = document.getElementById("tri-base").value;
          const height = document.getElementById("tri-height").value;
          const res = await api("/api/tool/area/triangle", {method:"POST", body:JSON.stringify({base, height}), headers:{"Content-Type":"application/json"}});
          document.getElementById("tri-res").textContent = res.area ?? res.error;
        });
      }
    });
  });
});

/* Helpers for works page */
async function loadFolders(){
  const el = document.getElementById("folders-list");
  el.textContent = "Loading...";
  const folders = await api("/api/folders");
  if (!folders.length) el.innerHTML = "<p>No folders</p>";
  else {
    el.innerHTML = folders.map(f => `<div class="folder-row">
      <strong>${f.name}</strong>
      <button onclick="deleteFolder(${f.id})">Delete</button>
      <button onclick="renameFolder(${f.id})">Rename</button>
    </div>`).join("");
  }
}

async function loadUploadFolders(){
  const sel = document.getElementById("upload-folder");
  const folders = await api("/api/folders");
  sel.innerHTML = `<option value="">-- root --</option>` + folders.map(f => `<option value="${f.id}">${f.name}</option>`).join("");
}

async function loadFiles(){
  const el = document.getElementById("files-list");
  el.textContent = "Loading...";
  const files = await api("/api/files");
  if (!files.length) el.innerHTML = "<p>No files</p>";
  else {
    el.innerHTML = files.map(f => `<div>
      <strong>${f.name}</strong> (${f.file_type})
      <button onclick="pickFile(${f.id})">Open</button>
      <button onclick="downloadFile(${f.id})">Download</button>
      <button onclick="deleteFile(${f.id})">Delete</button>
    </div>`).join("");
  }
}

async function pickFile(id){
  window.selectedFileId = id;
  const md = await api(`/api/files/${id}`);
  document.getElementById("file-meta").innerHTML = `<strong>${md.name}</strong> (${md.file_type})`;
  const contentResp = await api(`/api/file-content/${id}`);
  document.getElementById("file-content").value = contentResp.content || "";
  document.getElementById("run-output").textContent = "";
}

async function deleteFolder(id){
  if (!confirm("Delete folder and its files?")) return;
  await fetch(`/api/folders/${id}`, {method:"DELETE"});
  loadFolders(); loadFiles(); loadUploadFolders();
}

async function renameFolder(id){
  const newName = prompt("New folder name");
  if (!newName) return;
  await fetch(`/api/folders/${id}`, {method:"PUT", headers:{"Content-Type":"application/json"}, body:JSON.stringify({name:newName})});
  loadFolders(); loadUploadFolders();
}

async function deleteFile(id){
  if (!confirm("Delete file?")) return;
  await fetch(`/api/files/${id}`, {method:"DELETE"});
  loadFiles();
}

async function downloadFile(id){
  window.location = `/api/download/${id}`;
}
document.addEventListener('DOMContentLoaded', () => {
  const contactBtn = document.getElementById('contactBtn');
  const contactPopup = document.getElementById('contactPopup');
  const closePopupBtn = document.getElementById('closePopupBtn');

  contactBtn.addEventListener('click', () => {
    contactPopup.style.display = 'flex';
  });

  closePopupBtn.addEventListener('click', () => {
    contactPopup.style.display = 'none';
  });

  window.addEventListener('click', (e) => {
    if (e.target === contactPopup) {
      contactPopup.style.display = 'none';
    }
  });
});


