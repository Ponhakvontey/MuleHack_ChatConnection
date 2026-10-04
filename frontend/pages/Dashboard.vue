<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { logout } from '../services/auth.js'
import UserInformation from '../components/UserInformation.vue'
import PeoplePanel from '../components/PeoplePanel.vue'
import CallModal from '../components/CallModal.vue'
import { newCallState } from '../runtime/calls.js'
const callState = reactive(newCallState())
import { initializeChat } from '../runtime/chat.js'
const props = defineProps({ username: String, users: Array, chat_user: String })
const { username, users, chat_user } = props
const conversations = ref((users || []).map(u => ({ username: u[0] })))
const conversationQuery = ref('')
const visibleConversations = computed(() => conversations.value.filter(u => u.username.toLowerCase().includes(conversationQuery.value.toLowerCase())))
const selectedChat = ref(null)
const canSend = computed(() => conversations.value.find(u => u.username === selectedChat.value)?.can_message !== false)
function findPeople() { document.querySelector('[data-tab="contacts"]')?.click() }
function updateConversations(value) { conversations.value = value }
function openConversation(username) {
 document.querySelector('[data-tab="chats"]')?.click()
 disposeChat?.openConversation?.(username)
}
let disposeChat
const logoutError = ref('')
async function signOut() {
 logoutError.value = ''
 try { await logout() } catch (failure) { logoutError.value = failure.message }
}
onUnmounted(() => { disposeChat?.(); })
onMounted(() => {
 disposeChat = initializeChat({ chatUser: chat_user === null ? 'None' : chat_user, loggedInUser: username, callState, conversationUsers: users.map(u => u[0]), onConversationChange: user => { selectedChat.value = user } })
 if (sessionStorage.getItem('showUserInformation') === 'true') {
  sessionStorage.removeItem('showUserInformation')
  document.querySelector('[data-tab="profile"]')?.click()
 }
})
</script>

<template>
<div class="chat-app">
        <!-- Left Sidebar -->
        <div class="sidebar" id="sidebar">
            <div class="vertical-nav" id="verticalNav">
                <div class="nav-icon tab-swtich mb-3rem">
                    
                        <svg width="160" height="52" viewBox="0 0 160 52" fill="none" xmlns="http://www.w3.org/2000/svg">
                            <text x="0" y="40" font-family="'DM Sans', 'Open Sans', Arial Black, sans-serif"
                                font-size="42" font-weight="900" fill="#2860b0" letter-spacing="-1.5">Talk</text>
                            <text x="114" y="40" font-family="'DM Sans', 'Open Sans', Arial Black, sans-serif"
                                font-size="42" font-weight="900" fill="#0a1e3c" letter-spacing="-1.5">y</text>
                            <circle cx="148" cy="11" r="10" fill="#2860b0" opacity="0.2"/>
                            <circle cx="148" cy="11" r="6" fill="#2860b0"/>
                       
                    </svg>
                </div>
                                
                <div class="nav-icon has-badge active tab-swtich" data-tab="chats">
                    <i class="fas fa-comment-dots"></i><span class="badge" id="unreadBadge" style="display:none;"></span>
                </div>
                <div class="nav-icon tab-swtich" data-tab="profile" title="User Information" aria-label="User Information"><i class="fas fa-user"></i></div>
                <div class="nav-icon tab-swtich" data-tab="contacts"><i class="fas fa-book"></i></div>
                <div class="nav-icon tab-swtich" data-tab="favorites"><i class="fas fa-star"></i></div>
                <div class="nav-icon tab-swtich" data-tab="settings"><i class="fas fa-cog"></i></div>
                <div class="mt-auto">
                    <div class="profile-toggle-theme">
                        <button class="theme-toggle" id="themeToggle" title="Toggle Dark/Light Mode">
                            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                                stroke-width="2">
                                <circle cx="12" cy="12" r="5"></circle>
                                <line x1="12" y1="1" x2="12" y2="3"></line>
                                <line x1="12" y1="21" x2="12" y2="23"></line>
                                <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line>
                                <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line>
                                <line x1="1" y1="12" x2="3" y2="12"></line>
                                <line x1="21" y1="12" x2="23" y2="12"></line>
                                <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line>
                                <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>
                            </svg>
                        </button>
                        <div class="user-profile dropdown " id="userProfileBtn">
                            <button class="dropdown-btn" aria-haspopup="true" data-dir="right top" aria-expanded="false">
                                <div class="user-avatar-initial">{{ username[0]?.toUpperCase() }}</div>
                                <div class="profile-name">
                                    {{ username }}
                                </div>
                            </button>
                            
                            <ul class="dropdown-menu setting-menu" aria-label="Setting">
                                <li><a href="#" @click.prevent="signOut"><i class="fas fa-sign-out-alt"></i>Logout</a></li>
                                <li v-if="logoutError" role="alert">{{ logoutError }}</li>
                                <li>
                                    <a href="#"><i class="fas fa-info-circle"></i>Info</a>
                                </li>
                                <li>
                                    <a href="#"><i class="fas fa-cog"></i>Setting</a>
                                </li>
                                <li>
                                    <a href="#"><i class="fas fa-question-circle"></i>Help</a>
                                </li>
                            </ul>
                        </div>
                    </div>
                </div>
            </div>
            <div class="tab-panel" id="tab-chats">
                <div class="sidebar-header">
                    <h1 class="sidebar-title">Messages</h1>
                    <div class="search-container">
                        <svg class="search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none"
                            stroke="currentColor" stroke-width="2">
                            <circle cx="11" cy="11" r="8"></circle>
                            <path d="m21 21-4.35-4.35"></path>
                        </svg>
                        <input v-model="conversationQuery" type="text" class="search-input" placeholder="Search conversations...">
                    </div>
                    <div class="filter-tabs">
                        <button class="filter-tab active">All</button>
                        <button class="filter-tab">Group</button>
                        <button class="filter-tab">Unread</button>
                        <button class="filter-tab">Online</button>
                    </div>
                </div>
                <div class="sidebar-container">
                    <div class="users-list">
                        <template v-for="person in visibleConversations" :key="person.username"><template v-for="u in [[person.username]]" :key="u[0]">
                            <template v-if="u[0] !== username">

                            <div class="user-item" :data-user="u[0]">
                                
                                <div class="user-avatar online">
                                    {{ u[0][0]?.toUpperCase() }}
                                </div>

                                <div class="user-info">
                                    <div class="user-name">{{ u[0] }}</div>
                                    <div class="user-message">Start conversation...</div>
                                </div>

                                <div class="user-meta">
                                    <div class="message-time">--</div>
                                </div>

                            </div>

                            </template>
                        </template>
                        </template>
                        <div v-if="!conversations.length" class="conversation-empty" style="padding: 20px;">
                            <p>No conversations yet.</p><p>Find people and add friends to start chatting.</p>
                            <button class="profile-action-btn primary" @click="findPeople">Find People</button>
                        </div>
                    </div>
                </div>
            </div>

            <div class="tab-panel" id="tab-profile" hidden>
                <div class="sidebar-header banner">
                    <div class="title-bar">
                        <h1 class="settings-title">User Information</h1>
                        <div class="dropdown">
                            <button class="dropdown-menu-btn dropdown-btn" data-dir="left bottom"
                                aria-label="More options">
                                <i class="fas fa-ellipsis-v"></i>
                            </button>
                            <ul class="dropdown-menu setting-menu">
                                <li>
                                    <a href="#"><i class="fas fa-info-circle"></i>Info</a>
                                </li>
                                <li>
                                    <a href="#"><i class="fas fa-cog"></i>Setting</a>
                                </li>
                                <li>
                                    <a href="#"><i class="fas fa-question-circle"></i>Help</a>
                                </li>
                            </ul>
                        </div>
                    </div>
                    <div class="my-profile-avatar">
                        <div class="user-avatar-initial">{{ username[0]?.toUpperCase() }}</div>
                    </div>
                </div>
                <div class="sidebar-container">
                    <div class="auther-details">
                        <UserInformation :error="logoutError" @sign-out="signOut" />
                    </div>
                </div>
            </div>

            <div class="tab-panel" id="tab-contacts" hidden>
                <div class="sidebar-header"><h1 class="sidebar-title">Find People</h1></div>
                <div class="sidebar-container"><PeoplePanel @conversations="updateConversations" @message="openConversation" /></div>
            </div>

            <div class="tab-panel" id="tab-favorites" hidden>
<div class="sidebar-header"><h1 class="sidebar-title">Favorites</h1></div><div class="sidebar-container"><p style="padding:20px;">No saved favorites.</p></div>
</div>
            <div class="tab-panel" id="tab-settings" hidden>
                <div class="sidebar-header banner" id="backgroundOverlay">
                <div class="header-content">
                    <h1 class="settings-title">Settings</h1>
                    <button class="edit-btn">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                        <path d="m18.5 2.5 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                    </svg>
                    </button>
                    <input type="file" id="backgroundInput" accept="image/*" style="display: none;">
                </div>
                </div>
                <div class="profile-section">
                    <div class="profile-photo-container">
                    <div class="user-avatar-initial" id="profileImage">{{ username[0]?.toUpperCase() }}</div>
                    <button class="camera-btn">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
                        <circle cx="12" cy="13" r="4" />
                        </svg>
                    </button>
                    <input type="file" id="profileInput" accept="image/*" style="display: none;">
                    </div>
                </div>
                <div class="sidebar-container">
                    <!-- Settings Sections -->
                    <div class="settings-content">
                        <PeoplePanel blocked-only @conversations="updateConversations" />
                        <!-- Personal Info Section -->
                        <div class="accordion settings-section personal-info">
                            <div class="accordion__header section-header">
                                <div class="section-icon personal-info-icon">
                                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                                        stroke-width="2">
                                        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                                        <circle cx="12" cy="7" r="4" />
                                    </svg>
                                </div>
                                <span class="section-title">Personal Info</span>
                            </div>
                            <div class="accordion__panel section-content" id="personalInfoContent">
                                <div class="info-item">
                                    <label>Name</label>
                                    <input type="text" value="John Doe" class="info-input">
                                </div>
                                <div class="info-item">
                                    <label>Email</label>
                                    <input type="email" value="john.doe@example.com" class="info-input">
                                </div>
                                <div class="info-item">
                                    <label>Phone</label>
                                    <input type="tel" value="+1 234 567 8900" class="info-input">
                                </div>
                            </div>
                            <div class="accordion__header section-header">
                                <div class="section-icon privacy-icon">
                                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                                        stroke-width="2">
                                        <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                                        <circle cx="12" cy="16" r="1" />
                                        <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                                    </svg>
                                </div>
                                <span class="section-title">Privacy</span>
                            </div>

                            <div class="accordion__panel section-content">
                                <h3 class="privacy-subtitle">Who can see my personal info</h3>
                                <div class="privacy-item">
                                    <span class="privacy-label">Profile photo</span>
                                    <div class="custom-select">
                                        <select name="profile_photo" class="select-value">
                                            <option value="Everyone">Everyone</option>
                                            <option value="Contacts">Contacts</option>
                                            <option value="Nobody">Nobody</option>
                                        </select>
                                    </div>
                                </div>

                                <div class="privacy-item">
                                    <span class="privacy-label">Status</span>
                                    <div class="custom-select">
                                        <select name="profile_photo" class="select-value">
                                            <option value="Everyone">Everyone</option>
                                            <option value="Contacts">Contacts</option>
                                            <option value="Nobody">Nobody</option>
                                        </select>
                                    </div>
                                </div>

                                <div class="privacy-item">
                                    <span class="privacy-label">Groups</span>
                                    <div class="custom-select">
                                        <select name="profile_photo" class="select-value">
                                            <option value="Everyone">Everyone</option>
                                            <option value="Contacts">Contacts</option>
                                            <option value="Nobody">Nobody</option>
                                        </select>
                                    </div>
                                </div>

                                <div class="privacy-item toggle-item">
                                    <span class="privacy-label">Last seen</span>
                                    <label class="toggle">
                                        <input type="checkbox" checked>
                                        <span class="toggle-slider"></span>
                                    </label>
                                </div>

                                <div class="privacy-item toggle-item">
                                    <span class="privacy-label">Read receipts</span>
                                    <label class="toggle">
                                        <input type="checkbox" checked>
                                        <span class="toggle-slider"></span>
                                    </label>
                                </div>
                            </div>

                            <div class="accordion__header section-header">
                                <div class="section-icon security-icon">
                                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                                        stroke-width="2">
                                        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                                    </svg>
                                </div>
                                <span class="section-title">Security</span>
                            </div>
                            <div class="accordion__panel section-content">
                                <div class="security-item">
                                    <span class="security-label">Two-factor authentication</span>
                                    <label class="toggle">
                                        <input type="checkbox">
                                        <span class="toggle-slider"></span>
                                    </label>
                                </div>
                                <div class="security-item">
                                    <span class="security-label">Login alerts</span>
                                    <label class="toggle">
                                        <input type="checkbox" checked>
                                        <span class="toggle-slider"></span>
                                    </label>
                                </div>
                                <div class="security-item">
                                    <button class="security-button">Change Password</button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Main Chat Area -->
        <div class="chat-main" id="chatMain">
            <div v-if="!selectedChat" style="margin: auto; padding: 24px; text-align: center;">
                <h2>Welcome to Talky</h2><p>Add a friend or select a conversation to start messaging.</p>
            </div>
            <div v-show="selectedChat" class="chat-header">
                <div class="back-chat-auth">
                    <button class="mobile-back-btn" id="mobileBackBtn">
                        <i class="fas fa-arrow-left"></i>
                    </button>
                    <div class="chat-user-info" id="chatUserInfo">
                        <div class="chat-avatar currentChatAvatar">
                            {{ chat_user?.[0] }}   <!-- changed -->
                        </div>
                        <div class="chat-user-details">
                            <h3 class="currentChatName">{{ chat_user }}</h3>    <!-- changed -->
                            <div class="chat-user-status">Active now</div>
                        </div>
                    </div>
                </div>

                <div class="chat-actions">
                    <button class="action-btn" id="audioCallBtn">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                            stroke-width="2">
                            <path
                                d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z">
                            </path>
                        </svg>
                    </button>
                    <button class="action-btn" id="videoCallBtn">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                            stroke-width="2">
                            <polygon points="23 7 16 12 23 17 23 7"></polygon>
                            <rect x="1" y="5" width="15" height="14" rx="2" ry="2"></rect>
                        </svg>
                    </button>
                    <button class="action-btn" id="SearchBtn">
                        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none"
                            stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <circle cx="11" cy="11" r="8"></circle>
                            <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
                        </svg>
                    </button>

                     <div class="dropdown">
                        <button class="dropdown-btn action-btn" data-dir="bottom left" aria-label="More options">
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                                stroke-width="2">
                                <circle cx="12" cy="12" r="1"></circle>
                                <circle cx="19" cy="12" r="1"></circle>
                                <circle cx="5" cy="12" r="1"></circle>
                            </svg>
                        </button>
                        <ul class="dropdown-menu setting-menu chat-setting-option">
                            <li>
                                <a href="#">Archive <i class="fa-solid fa-box-archive"></i></a>
                            </li>
                            <li>
                                <a href="#">Muted <i class="fa-solid fa-volume-xmark"></i></a>
                            </li>
                             <li>
                                <a href="#">Delete Chat <i class="fa-solid fa-trash-can"></i></a>
                            </li>
                            <li>
                                <a href="#">Close Chat <i class="fa-solid fa-folder-closed"></i></a>
                            </li>
                        </ul>
                    </div>
                </div>
            </div>

            <div v-show="selectedChat" class="chat-messages" id="chatMessages"></div>

            <!-- File Preview Area -->
            <div class="file-preview" id="filePreview"></div>

            <p v-if="selectedChat && !canSend" role="status" style="padding: 16px;">Messaging is unavailable. Become friends to exchange new messages.</p>
            <div v-show="selectedChat && canSend" class="chat-input">
                <div class="input-container">
                    <div class="input-actions">
                        <!-- Hidden file input for general files -->
                        <input type="file" id="fileInput" accept="*/*" class="file-input">
                        <button class="input-action-btn" id="attachFileBtn" title="Attach File">
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                                stroke-width="2">
                                <path
                                    d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66L9.64 16.2a2 2 0 0 1-2.83-2.83l8.49-8.49">
                                </path>
                            </svg>
                        </button>
                        <input type="file" id="imageInput" accept="image/*" class="file-input">
                        <button class="input-action-btn" id="sendImageBtn" title="Send Image">
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                                stroke-width="2">
                                <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                                <circle cx="8.5" cy="8.5" r="1.5"></circle>
                                <polyline points="21,15 16,10 5,21"></polyline>
                            </svg>
                        </button>
                    </div>
                    <textarea class="message-input" placeholder="Type a message..." rows="1"
                        id="messageInput"></textarea>
                    <button class="input-action-btn" id="sendAudioBtn" title="Voice record">
                        <svg fill="currentColor" width="16" height="16" version="1.1" xmlns="http://www.w3.org/2000/svg"
                            viewBox="0 0 512 512" xmlns:xlink="http://www.w3.org/1999/xlink"
                            enable-background="new 0 0 512 512">
                            <g>
                                <g>
                                    <path
                                        d="m439.5,236c0-11.3-9.1-20.4-20.4-20.4s-20.4,9.1-20.4,20.4c0,70-64,126.9-142.7,126.9-78.7,0-142.7-56.9-142.7-126.9 0-11.3-9.1-20.4-20.4-20.4s-20.4,9.1-20.4,20.4c0,86.2 71.5,157.4 163.1,166.7v57.5h-23.6c-11.3,0-20.4,9.1-20.4,20.4 0,11.3 9.1,20.4 20.4,20.4h88c11.3,0 20.4-9.1 20.4-20.4 0-11.3-9.1-20.4-20.4-20.4h-23.6v-57.5c91.6-9.3 163.1-80.5 163.1-166.7z" />
                                    <path
                                        d="m256,323.5c51,0 92.3-41.3 92.3-92.3v-127.9c0-51-41.3-92.3-92.3-92.3s-92.3,41.3-92.3,92.3v127.9c0,51 41.3,92.3 92.3,92.3zm-52.3-220.2c0-28.8 23.5-52.3 52.3-52.3s52.3,23.5 52.3,52.3v127.9c0,28.8-23.5,52.3-52.3,52.3s-52.3-23.5-52.3-52.3v-127.9z" />
                                </g>
                            </g>
                        </svg>
                    </button>
                    <button class="send-button" id="sendButton" title="Send">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                            stroke-width="2">
                            <line x1="22" y1="2" x2="11" y2="13"></line>
                            <polygon points="22,2 15,22 11,13 2,9"></polygon>
                        </svg>
                    </button>
                </div>
            </div>
        </div>

        <!-- Mobile Bottom Navigation -->
        <div class="mobile-bottom-nav" id="mobileBottomNav">
            <div class="mobile-nav-icon active tab-swtich" data-tab="chats">
                <i class="fas fa-comment-dots"></i>
                <span>Chats</span>
            </div>
            <div class="mobile-nav-icon tab-swtich" data-tab="contacts">
                <i class="fas fa-book"></i>
                <span>Contacts</span>
            </div>
            <div class="mobile-nav-icon tab-swtich" data-tab="favorites">
                <i class="fas fa-star"></i>
                <span>Favorites</span>
            </div>
            <div class="mobile-nav-icon tab-swtich" data-tab="settings">
                <i class="fas fa-cog"></i>
                <span>Settings</span>
            </div>
        </div>

        <!-- Right Sidebar - User Details -->
        <div class="right-sidebar" id="rightSidebar">
            <div class="right-sidebar-header">
                <h2 class="right-sidebar-title">Contact Info</h2>
                <button class="close-right-sidebar" id="closeRightSidebar">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <line x1="18" y1="6" x2="6" y2="18"></line>
                        <line x1="6" y1="6" x2="18" y2="18"></line>
                    </svg>
                </button>
            </div>
            <div class="right-sidebar-content">
                <div class="user-profile-section">
                    <div class="profile-avatar online currentChatAvatar">{{ selectedChat?.[0]?.toUpperCase() }}</div>
                    <div class="profile-name currentChatName">{{ selectedChat }}</div>
                    <div class="profile-status">Active now</div>
                    <div class="profile-actions">
                        <button class="profile-action-btn primary">Message</button>
                        <button class="profile-action-btn" id="profileAudioBtn">Call</button>
                        <button class="profile-action-btn" id="profileVideoBtn">Video</button>
                    </div>
                </div>
                <div class="members-section">
                    <div class="section-header">
                        <div class="section-title">Participants</div>
                        <a href="#" class="section-action">Add Member</a>
                    </div>
                    <div class="members-list"></div>
                </div>
                <div class="section">
                    <div class="section-header">
                        <div class="section-title">Shared Media</div>
                        <a href="#" class="section-action">See All</a>
                    </div>
                    <div class="section-content">
                        <div class="media-grid"></div>
                    </div>
                </div>
                <div class="section">
                    <div class="section-header">
                        <div class="section-title">Shared Files</div>
                        <a href="#" class="section-action">See All</a>
                    </div>
                    <div class="section-content">
                        <div class="file-list"></div>
                    </div>
                </div>
                <div class="section">
                    <div class="settings-list">
                        <div class="settings-item">
                            <svg class="settings-icon" width="20" height="20" viewBox="0 0 24 24" fill="none"
                                stroke="currentColor" stroke-width="2">
                                <path d="M18.36 6.64a9 9 0 1 1-12.73 0"></path>
                                <line x1="12" y1="2" x2="12" y2="12"></line>
                            </svg>
                            <div class="settings-text">Mute Notifications</div>
                        </div>
                        <div class="settings-item">
                            <svg class="settings-icon" width="20" height="20" viewBox="0 0 24 24" fill="none"
                                stroke="currentColor" stroke-width="2">
                                <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"></path>
                                <circle cx="9" cy="7" r="4"></circle>
                                <path d="M22 21v-2a4 4 0 0 0-3-3.87"></path>
                                <path d="M16 3.13a4 4 0 0 1 0 7.75"></path>
                            </svg>
                            <div class="settings-text">Group Settings</div>
                        </div>
                        <div class="settings-item">
                            <svg class="settings-icon" width="20" height="20" viewBox="0 0 24 24" fill="none"
                                stroke="currentColor" stroke-width="2">
                                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path>
                                <polyline points="16,17 21,12 16,7"></polyline>
                                <line x1="21" y1="12" x2="9" y2="12"></line>
                            </svg>
                            <div class="settings-text danger">Leave Group</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <div class="right-sidebar" id="searchSidebar">
            <div class="right-sidebar-header">
                <h2 class="right-sidebar-title">Search</h2>
                <button class="close-right-sidebar" id="closeSearchSidebar">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <line x1="18" y1="6" x2="6" y2="18"></line>
                        <line x1="6" y1="6" x2="18" y2="18"></line>
                    </svg>
                </button>
            </div>
            <div class="right-sidebar-content">
                <div class="search-result-container">
                    <div class="search-bar">
                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 30 30" width="20px" height="20px">
                            <path
                                d="M 13 3 C 7.4889971 3 3 7.4889971 3 13 C 3 18.511003 7.4889971 23 13 23 C 15.396508 23 17.597385 22.148986 19.322266 20.736328 L 25.292969 26.707031 A 1.0001 1.0001 0 1 0 26.707031 25.292969 L 20.736328 19.322266 C 22.148986 17.597385 23 15.396508 23 13 C 23 7.4889971 18.511003 3 13 3 z M 13 5 C 17.430123 5 21 8.5698774 21 13 C 21 17.430123 17.430123 21 13 21 C 8.5698774 21 5 17.430123 5 13 C 5 8.5698774 8.5698774 5 13 5 z" />
                        </svg>
                        <input type="search" placeholder="Search" value="" />
                    </div>
                    <div class="result">
                        <div class="search-date">15/4/2025</div>
                        <div class="search-message">hi</div>
                    </div>
                    <div class="result">
                        <div class="search-date">6/4/2025</div>
                        <div class="search-message">How are you?</div>
                    </div>
                    <div class="result">
                        <div class="search-date">22/3/2025</div>
                        <div class="search-message">Hello</div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    <CallModal :state="callState" :username="username" />

    <!-- Mobile Overlays -->
    <div class="overlay" id="overlay"></div>
    <div class="right-overlay" id="rightOverlay"></div>

    <div class="gallery-modal" id="galleryModal">
        <div class="gallery-close" id="galleryClose">
            <i class="fas fa-times"></i>
        </div>
        <div class="gallery-nav prev" id="galleryPrev">
            <i class="fas fa-chevron-left"></i>
        </div>
        <div class="gallery-content" id="galleryContent">
            <!-- Content will be inserted here dynamically -->
        </div>
        <div class="gallery-nav next" id="galleryNext">
            <i class="fas fa-chevron-right"></i>
        </div>
        <div class="gallery-index" id="galleryIndex"></div>
        <div class="gallery-download" id="galleryDownload" title="Download">
            <i class="fas fa-download"></i>
        </div>
    </div>

<!-- Define chatUser from Flask template -->


<!-- Load your crypto logic -->


<!-- Load your chat logic (handles send button, receive messages, etc.) -->
</template>
