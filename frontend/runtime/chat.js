import { backendFetch as fetch, backendUrl, authState } from '../services/auth.js'
import { createCallController } from './calls.js'
import { generateAESKey, encryptMessage, decryptMessage } from './crypto.js'
import { attachThreatWarnings } from './threatWarnings.js'

// Keep existing handlers and protocol logic; run DOM-ready work after Vue mounts.
export function initializeChat({ chatUser, loggedInUser, callState, conversationUsers = [], onConversationChange = () => {} }) {
const registrations = []
const originalAdd = EventTarget.prototype.addEventListener
EventTarget.prototype.addEventListener = function(type, callback, options) {
 registrations.push([this, type, callback, options])
 return originalAdd.call(this, type, callback, options)
}
try {
const readyCallbacks = []
const onReady = callback => readyCallbacks.push(callback)
﻿console.log("chat.js loaded");

let activeReceiver = null;  // track who you're chatting with

const wsLocation = new URL(backendUrl('/ws'));
wsLocation.protocol = wsLocation.protocol === 'https:' ? 'wss:' : 'ws:';
const wsUrl = wsLocation.href;

let mediaRecorder;
let audioChunks = [];
let isRecording = false;

let videoPc;  
let localVideoStream;
let videoCallStartTime;
let videoDurationInterval;

const audioBtn = document.getElementById("sendAudioBtn");
// WebSocket connection
let socket;
try {
  socket = new WebSocket(wsUrl);

  // Handshake: send username immediately after connecting
  socket.addEventListener("open", () => {
    console.log("[DEBUG] WebSocket connected as", loggedInUser);
    socket.send(loggedInUser); // backend expects this first
  });

  socket.addEventListener("error", (err) => authState.signingOut || console.error("[DEBUG] WebSocket error:", err));
  socket.addEventListener("close", (e) => authState.signingOut || console.warn("[DEBUG] WebSocket closed:", e));
} catch (err) {
  console.error("[DEBUG] Failed to create WebSocket:", err);
}

const ICE_SERVERS = [
  { urls: "stun:stun.l.google.com:19302" },
  {
    urls: "turn:openrelay.metered.ca:80",
    username: "openrelayproject",
    credential: "openrelayproject"
  },
  {
    urls: "turn:openrelay.metered.ca:443",
    username: "openrelayproject",
    credential: "openrelayproject"
  },
  {
    urls: "turn:openrelay.metered.ca:443?transport=tcp",
    username: "openrelayproject",
    credential: "openrelayproject"
  }
];

const calls = createCallController({ state: callState, username: loggedInUser, iceServers: ICE_SERVERS,
 onEnd: (type, duration) => addCallLogToUI(`${type === 'video' ? '📹 Video call' : '📞 Call'} ended • ${String(Math.floor(duration / 60)).padStart(2, '0')}:${String(duration % 60).padStart(2, '0')}`),
 send: message => { if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify(message)); else throw new Error('Call connection unavailable') }
})
socket.addEventListener('close', () => calls.fail())
for (const [id, type] of [['audioCallBtn', 'audio'], ['videoCallBtn', 'video'], ['profileAudioBtn', 'audio'], ['profileVideoBtn', 'video']]) {
 document.getElementById(id)?.addEventListener('click', () => calls.start(type, activeReceiver))
}

onReady( async () => {
  try {
    const savedChatUser = localStorage.getItem("lastChatUser");
    const initialUser = conversationUsers.includes(chatUser) ? chatUser : savedChatUser;
    if (initialUser && conversationUsers.includes(initialUser)) {
      await generateAESKey(initialUser);
      loadChatHistory(initialUser);
    }
  } catch (err) {
    console.error("[DEBUG] Failed to initialize AES key:", err);
  }
});

// decrypt message before displaying (receiver side)
socket.onmessage = async (event) => {
  try {
    const msg = JSON.parse(event.data);
    if (await calls.handle(msg)) return;
    if (msg.type === 'error') {
      calls.fail()
      alert(msg.error)
      window.dispatchEvent(new Event('talky:relationships-changed'))
      if (activeReceiver) await loadChatHistory(activeReceiver)
      return
    }

    if (msg.type === "file" || msg.type === "image") {
      const _imgExts = ["jpg", "jpeg", "png", "gif", "webp"];
      const _who = msg.sender === loggedInUser ? "Me" : msg.sender;
      if (msg.type === "image") {
        addMessageToUI(_who, makeMediaNode('img', msg.url), null);
      } else {
        const _ext = (msg.url || "").split(".").pop().split("?")[0].toLowerCase();
        if (_imgExts.includes(_ext)) {
          addMessageToUI(_who, makeMediaNode('img', msg.url), null);
        } else {
          addMessageToUI(_who, makeMediaNode('file', msg.url), null);
        }
      }
      return;
    }

    // Add audio handling here
    if (msg.type === "audio") {
      const audio = document.createElement("audio");
      audio.controls = true;
      audio.src = msg.url;
      document.getElementById("chatMessages").appendChild(audio);
      return;
    }

    // Text message + decryption
    if (msg.type === "text") {
      const chatPartner = msg.sender === loggedInUser ? msg.receiver : msg.sender;
      // Ensure we have a key for this conversation (may arrive before user opens chat)
      if (!_aesKeyMap[chatPartner]) {
        try { await generateAESKey(chatPartner); } catch (_) {}
      }
      let plaintext;
      try {
        plaintext = await decryptMessage(msg.ciphertext, msg.nonce, chatPartner);
      } catch (err) {
        console.error("[DEBUG] Failed to decrypt text message:", err, msg);
        plaintext = "[Decryption failed]";
      }
      // Only render in chat if this is the active conversation
      if (chatPartner === activeReceiver) {
        addMessageToUI(msg.sender === loggedInUser ? "Me" : msg.sender, plaintext, msg.timestamp);
      }
      return;
    }


  } catch (err) {
    console.error("[DEBUG] Failed to process incoming message:", err, event.data);
  }
};

// Reusable function to fetch and render history
async function loadChatHistory(user) {
  activeReceiver = user;
  onConversationChange(user);
  localStorage.setItem("lastChatUser", user);

  // Update header
  document.querySelector(".currentChatName").textContent = user;
  document.querySelector(".currentChatAvatar").textContent = user[0].toUpperCase();

  // Clear chat window
  const chatBox = document.getElementById("chatMessages");
  chatBox.innerHTML = "";

  try {
    const res = await fetch(`/messages/${user}`);
    console.log("Fetch response status:", res.status);

    if (!res.ok) {
      console.error("[DEBUG] Failed to fetch history:", res.status);
      return;
    }

    const history = await res.json();
    console.log("Fetched history for", user, ":", history);

    let lastPreview = null;
    let lastMsgTime = null;

    for (const msg of history) {
      const who = msg.sender === loggedInUser ? "Me" : msg.sender;
      lastMsgTime = msg.timestamp;

      if (msg.msg_type === "text") {
        let plaintext;
        try {
          plaintext = await decryptMessage(msg.ciphertext, msg.nonce);
        } catch (err) {
          console.error("[DEBUG] Decryption failed:", err, msg);
          plaintext = "[Decryption failed]";
        }
        addMessageToUI(who, plaintext, msg.timestamp);
        lastPreview = plaintext.length > 40 ? plaintext.slice(0, 40) + "..." : plaintext;

      } else if (msg.msg_type === "file") {
        const imgExts = ["jpg", "jpeg", "png", "gif", "webp"];
        const ext = (msg.file_name || "").split(".").pop().toLowerCase();
        if (imgExts.includes(ext)) {
          addMessageToUI(who, makeMediaNode('img', '/uploads/' + msg.file_name), msg.timestamp);
          lastPreview = "Photo";
        } else {
          addMessageToUI(who, makeMediaNode('file', '/uploads/' + msg.file_name), msg.timestamp);
          lastPreview = "File";
        }

      } else if (msg.msg_type === "image") {
        addMessageToUI(who, makeMediaNode('img', '/uploads/' + msg.file_name), msg.timestamp);
        lastPreview = "Photo";

      } else if (msg.msg_type === "audio") {
        addMessageToUI(who, makeMediaNode('audio', '/uploads/' + msg.file_name), msg.timestamp);
        lastPreview = "Voice message";

      } else if (msg.msg_type === "call") {
        let callInfo = "";
        if (msg.status === "ended") {
          const secs = msg.duration || 0;
          const mm = String(Math.floor(secs / 60)).padStart(2, "0");
          const ss = String(secs % 60).padStart(2, "0");
          callInfo = "Call ended " + mm + ":" + ss;
          lastPreview = callInfo;
        } else if (msg.status === "missed") {
          callInfo = "Missed call from " + msg.sender;
          lastPreview = callInfo;
        } else if (msg.status === "declined") {
          callInfo = "Call declined";
          lastPreview = callInfo;
        }
        if (callInfo) addCallLogToUI(callInfo, msg.timestamp);
      }
    }

    // Update sidebar user-item preview
    const sidebarItem = document.querySelector('.user-item[data-user="' + user + '"]');
    if (sidebarItem) {
      const msgEl = sidebarItem.querySelector(".user-message");
      if (msgEl && lastPreview) msgEl.textContent = lastPreview;
      const timeEl = sidebarItem.querySelector(".message-time");
      if (timeEl && lastMsgTime) timeEl.textContent = formatTimestamp(lastMsgTime);
    }

  } catch (err) {
    console.error("[DEBUG] Error loading chat history:", err);
  }

  console.log("Restored chat with", user);
}

// Sidebar click → load history and set receiver
document.addEventListener("click", (e) => {
  const item = e.target.closest(".user-item");
  if (item) {
    const user = item.dataset.user;
    console.log("[DEBUG] Sidebar clicked:", item, user);
    if (user) {
      activeReceiver = user;
      console.log("[DEBUG] activeReceiver set to:", activeReceiver);
      document.querySelectorAll('.user-item').forEach(el => el.classList.remove('active'));
      item.classList.add('active');
      generateAESKey(user).then(() => loadChatHistory(user)).catch(err => {
        console.error("[DEBUG] Failed to init AES key for", user, err);
        loadChatHistory(user);
      });
    } else {
      console.warn("[DEBUG] Clicked user-item without data-user attribute");
    }
  }
});

// Add message bubble to UI
function formatTimestamp(ts) {
  if (!ts) return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const d = new Date(ts);
  if (isNaN(d)) return ts;
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function safeMediaUrl(url) {
  if (!url) return null;
  if (url.startsWith('/uploads/')) return backendUrl(url);
  try {
    const p = new URL(url, window.location.origin);
    if (p.protocol === 'https:' || p.protocol === 'http:') return url;
  } catch (_) {}
  return null;
}

function makeMediaNode(type, url, filename) {
  const safe = safeMediaUrl(url);
  if (type === 'img') {
    const img = document.createElement('img');
    img.src = safe || '';
    img.style.maxWidth = '200px';
    img.style.borderRadius = '8px';
    return img;
  }
  if (type === 'audio') {
    const aud = document.createElement('audio');
    aud.controls = true;
    aud.src = safe || '';
    return aud;
  }
  // file link
  const a = document.createElement('a');
  a.href = safe || '#';
  a.target = '_blank';
  a.rel = 'noopener noreferrer';
  a.textContent = filename || 'Download file';
  return a;
}

function addMessageToUI(sender, content, timestamp=null) {
  const chatBox = document.getElementById("chatMessages");
  const messageDiv = document.createElement("div");
  messageDiv.className = sender === "Me" ? "message sent" : "message received";

  const wrapper = document.createElement("div");
  wrapper.className = "message-wrapper";

  const contentDiv = document.createElement("div");
  contentDiv.className = "message-content";

  const textDiv = document.createElement("div");
  textDiv.className = "message-text";

  if (content instanceof Node) {
    textDiv.appendChild(content);
  } else {
    textDiv.textContent = String(content);
  }

  contentDiv.appendChild(textDiv);
  if (typeof content === 'string') {
    try { attachThreatWarnings(contentDiv, content); } catch (_) { /* Security additions must not interrupt chat. */ }
  }

  const tsDiv = document.createElement("div");
  tsDiv.className = "message-timestamp";
  tsDiv.textContent = formatTimestamp(timestamp);

  wrapper.appendChild(contentDiv);
  wrapper.appendChild(tsDiv);
  messageDiv.appendChild(wrapper);
  chatBox.appendChild(messageDiv);
  chatBox.scrollTop = chatBox.scrollHeight;
}

function addCallLogToUI(callInfo, timestamp=null) {
  const chatBox = document.getElementById("chatMessages");
  const div = document.createElement("div");
  div.className = "message call-log";

  const content = document.createElement("div");
  content.className = "call-log-content";

  const text = document.createElement("span");
  text.className = "call-log-text";
  text.textContent = callInfo;

  const time = document.createElement("span");
  time.className = "call-log-time";
  time.textContent = formatTimestamp(timestamp);

  content.appendChild(text);
  content.appendChild(time);
  div.appendChild(content);
  chatBox.appendChild(div);
  chatBox.scrollTop = chatBox.scrollHeight;
}

// Send button + encrypt the message
document.getElementById("sendButton").addEventListener("click", async () => {
  const input = document.getElementById("messageInput");
  const message = input.value.trim();

  if (message !== "" && activeReceiver) {
    try {
      // Encrypt with AES before sending
      const { ciphertext, nonce } = await encryptMessage(message);

      socket.send(JSON.stringify({
        receiver: activeReceiver,
        ciphertext,
        nonce
      }));

      // Show plaintext locally with current time
      addMessageToUI("Me", message, new Date().toISOString());
      input.value = "";
    } catch (err) {
      console.error("[DEBUG] Failed to send message:", err);
    }
  }
});

// Support Enter key
document.getElementById("messageInput").addEventListener("keypress", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    document.getElementById("sendButton").click();
  }
});

// File and image upload handlers
onReady( () => {
    const attachFileBtn = document.getElementById("attachFileBtn");
    const fileInput = document.getElementById("fileInput");
    const sendImageBtn = document.getElementById("sendImageBtn");
    const imageInput = document.getElementById("imageInput");
    const filePreview = document.getElementById("filePreview");

    // Attach File button → open file picker
    attachFileBtn.addEventListener("click", () => {
        console.log("[DEBUG] attachFileBtn clicked");
        if (!fileInput) {
            console.error("[DEBUG] fileInput element not found!");
            return;
        }
        fileInput.click();
    });

    fileInput.addEventListener("change", () => {
        console.log("[DEBUG] fileInput onchange triggered");
        if (fileInput.files.length > 0) {
            const file = fileInput.files[0];
            console.log("[DEBUG] Selected file:", file.name);
            previewFile(file);
            if (file.type.startsWith("image/")) {
                sendImage(file);
            } else {
                sendFile(file);
            }
        } else {
            console.warn("[DEBUG] No file selected");
        }
    });

    // Send Image button → open image picker
    sendImageBtn.addEventListener("click", () => {
        console.log("[DEBUG] sendImageBtn clicked");
        if (!imageInput) {
            console.error("[DEBUG] imageInput element not found!");
            return;
        }
        imageInput.click();
    });

    imageInput.addEventListener("change", () => {
        console.log("[DEBUG] imageInput onchange triggered");
        if (imageInput.files.length > 0) {
            const image = imageInput.files[0];
            console.log("[DEBUG] Selected image:", image.name);
            // Show preview
            previewFile(image);
            // upload
            sendImage(image);
        } else {
            console.warn("[DEBUG] No image selected");
        }
    });
        // Preview function
    function previewFile(file) {
        const reader = new FileReader();
        reader.onload = function(e) {
            if (file.type.startsWith("image/")) {
                filePreview.innerHTML = `<img src="${e.target.result}" alt="${file.name}" style="max-width:150px; max-height:150px;">`;
            } else {
                filePreview.innerHTML = `<p>Selected file: ${file.name}</p>`;
            }
        };
        reader.readAsDataURL(file);
    }
        // 🔹 User list → Chat board toggle
    document.querySelectorAll('.user-list .user').forEach(user => {
        user.addEventListener('click', () => {
            document.querySelector('.user-list').style.display = 'none';
            document.querySelector('.chat-board').classList.add('active');
        });
    });

    // 🔹 Swipe gesture for mobile
    const chatBoard = document.querySelector('.chat-board');
    let touchStartX = 0;
    let touchEndX = 0;

    if (chatBoard) {
      chatBoard.addEventListener('touchstart', (e) => {
        touchStartX = e.changedTouches[0].screenX;
      });

      chatBoard.addEventListener('touchend', (e) => {
        touchEndX = e.changedTouches[0].screenX;
        handleSwipe();
      });
    }

    function handleSwipe() {
      const swipeDistance = touchStartX - touchEndX;

      // Adjust threshold (e.g., 50px) to avoid accidental triggers
      if (swipeDistance > 50) {
        console.log("[DEBUG] Swipe left detected → back to user list");
        chatBoard.classList.remove('active');
        document.querySelector('.user-list').style.display = 'block';
      }
    }
});

// Audio upload handlers
onReady( () => {
    const sendAudioBtn = document.getElementById("sendAudioBtn");

    sendAudioBtn.addEventListener("click", () => {
        console.log("[DEBUG] sendAudioBtn clicked");
        startRecording();
    });
});

// send file to backend, get URL, render link, and notify receiver via WebSocket
function sendFile(file) {
    console.log("[DEBUG] sendFile() called with:", file);
    if (!activeReceiver) {
      console.error("[DEBUG] No activeReceiver set! Cannot upload file.");
      return;
    }
    const formData = new FormData();
    formData.append("file", file);
    formData.append("receiver", activeReceiver);

    console.log("[DEBUG] FormData prepared. Receiver:", activeReceiver);

    fetch("/upload_file", { method: "POST", body: formData })
        .then(res => {
            console.log("[DEBUG] Upload response status:", res.status);
            console.log("[DEBUG] Upload response headers:", [...res.headers.entries()]);
            return res.text();  // read raw text first
        })
        .then(text => {
            console.log("[DEBUG] Raw response body:", text);
            try {
                const data = JSON.parse(text);
                console.log("[DEBUG] Parsed JSON:", data);

                const _fileNode = makeMediaNode('file', data.url, data.url.endsWith('.pdf') ? 'Open PDF' : 'Download file');
                addMessageToUI("Me", _fileNode, new Date().toISOString());
                // Send to receiver via WebSocket
                socket.send(JSON.stringify({
                    type: "file",
                    sender: loggedInUser,
                    receiver: activeReceiver,
                    url: data.url
                }));
            } catch (err) {
                console.error("[DEBUG] Failed to parse JSON:", err);
            }
        })
        .catch(err => console.error("[DEBUG] Upload error:", err));
}

// sendimages. Backend returns URL, we render the image and notify receiver.
function sendImage(image) {
    console.log("[DEBUG] sendImage() called with:", image);
    if (!activeReceiver) {
      console.error("[DEBUG] No activeReceiver set! Cannot upload image.");
      return;
    }

    const formData = new FormData();
    formData.append("image", image);
    formData.append("receiver", activeReceiver);

    console.log("[DEBUG] FormData prepared. Receiver:", activeReceiver);

    fetch("/upload_image", { method: "POST", body: formData })
        .then(res => {
            console.log("[DEBUG] Upload response status:", res.status);
            console.log("[DEBUG] Upload response headers:", [...res.headers.entries()]);
            return res.text();  // read raw text first
        })
        .then(text => {
            console.log("[DEBUG] Raw response body:", text);
            try {
                const data = JSON.parse(text);
                console.log("[DEBUG] Parsed JSON:", data);

                // Render immediately for sender (aligned right)
                addMessageToUI("Me", makeMediaNode('img', data.url), new Date().toISOString());

                socket.send(JSON.stringify({
                    type: "image",
                    sender: loggedInUser,
                    receiver: activeReceiver,
                    url: data.url
                }));
                console.log("[DEBUG] WebSocket message sent for image:", data.url);
            } catch (err) {
                console.error("[DEBUG] Failed to parse JSON:", err);
            }
        })
        .catch(err => console.error("[DEBUG] Upload error:", err));
}

audioBtn.addEventListener("click", () => {
    if (!isRecording) {
        startRecording();
        audioBtn.textContent = "⏹ Stop"; // change icon/text
    } else {
        stopRecording();
        audioBtn.textContent = "🎤 Record"; // reset icon/text
    }
    isRecording = !isRecording;
});

function startRecording() {
    navigator.mediaDevices.getUserMedia({ audio: true })
        .then(stream => {
            mediaRecorder = new MediaRecorder(stream);
            mediaRecorder.start();
            audioChunks = [];

            mediaRecorder.ondataavailable = e => audioChunks.push(e.data);

            mediaRecorder.onstop = () => {
                const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
                sendAudio(audioBlob);
            };

            // Optional: auto‑stop after 60s max
            setTimeout(() => {
                if (isRecording) {
                    stopRecording();
                    audioBtn.textContent = "🎤 Record";
                    isRecording = false;
                }
            }, 60000);
        })
        .catch(err => console.error("Microphone error:", err));
}

function stopRecording() {
    if (mediaRecorder && mediaRecorder.state !== "inactive") {
        mediaRecorder.stop();
    }
}

// Send audio blob to backend, get URL, render audio player, and notify receiver via WebSocket
function sendAudio(audioBlob) {
    console.log("[DEBUG] sendAudio() called with:", audioBlob);
    if (!activeReceiver) {
        console.error("[DEBUG] No activeReceiver set! Cannot upload audio.");
        return;
    }

    const formData = new FormData();
    formData.append("audio", audioBlob, "voiceMessage.webm");
    formData.append("receiver", activeReceiver);

    console.log("[DEBUG] FormData prepared. Receiver:", activeReceiver);

    fetch("/upload_audio", { method: "POST", body: formData })
        .then(res => {
            console.log("[DEBUG] Upload response status:", res.status);
            return res.text();
        })
        .then(text => {
            console.log("[DEBUG] Raw response body:", text);
            try {
                const data = JSON.parse(text);
                console.log("[DEBUG] Parsed JSON:", data);

                // Render immediately for sender (aligned right)
                addMessageToUI("Me", makeMediaNode('audio', data.url), new Date().toISOString());

                // Send to receiver via WebSocket
                socket.send(JSON.stringify({
                    type: "audio",
                    sender: loggedInUser,
                    receiver: activeReceiver,
                    url: data.url
                }));
                console.log("[DEBUG] WebSocket message sent for audio:", data.url);
            } catch (err) {
                console.error("[DEBUG] Failed to parse JSON:", err);
            }
        })
        .catch(err => console.error("[DEBUG] Upload error:", err));
}

// ---- Tab switching for sidebar nav icons ----
onReady( () => {
  document.querySelectorAll(".tab-swtich").forEach(el => {
    el.addEventListener("click", () => {
      const tab = el.dataset.tab;
      if (!tab) return;
      document.querySelectorAll(".nav-icon.tab-swtich, .mobile-nav-icon.tab-swtich").forEach(n => n.classList.remove("active"));
      el.classList.add("active");
      document.querySelectorAll(".tab-panel").forEach(p => { p.hidden = (p.id !== ("tab-" + tab)); });
    });
  });

  // Dropdown positioning and toggle
  document.addEventListener("click", (e) => {
    const btn = e.target.closest(".dropdown-btn");
    if (btn) {
      e.stopPropagation();
      const dropdown = btn.closest(".dropdown");
      const menu = dropdown && dropdown.querySelector(".dropdown-menu");
      if (!menu) return;
      const isOpen = menu.classList.contains("show");
      document.querySelectorAll(".dropdown-menu.show").forEach(m => m.classList.remove("show"));
      if (!isOpen) {
        const rect = btn.getBoundingClientRect();
        menu.style.top = (rect.bottom + 4) + "px";
        menu.style.left = (rect.left - menu.offsetWidth + rect.width) + "px";
        menu.classList.add("show");
      }
      return;
    }
    // Outside click closes all
    if (!e.target.closest(".dropdown-menu")) {
      document.querySelectorAll(".dropdown-menu.show").forEach(m => m.classList.remove("show"));
    }
  });
});
for (const callback of readyCallbacks) callback()
const dispose = () => {
 for (const [target, type, callback, options] of registrations) target.removeEventListener(type, callback, options)
 calls.dispose()
 socket?.close()
 if (mediaRecorder?.state === 'recording') mediaRecorder.stop()
}
dispose.openConversation = async user => {
 await generateAESKey(user)
 await loadChatHistory(user)
}
return dispose
} finally { EventTarget.prototype.addEventListener = originalAdd }
}
