// Memory Lane for the Mac: a menu bar app that holds the companion in a small floating window.
// It loads the live site, so an update to the site reaches the app without reinstalling.
const {
  app, BrowserWindow, Tray, Menu, globalShortcut, nativeImage, session, shell, screen, systemPreferences, ipcMain,
} = require("electron");
const fs = require("fs");
const path = require("path");

const APP_URL = process.env.ML_URL || "https://elder-companion-seven.vercel.app/app";
const ORIGIN = new URL(APP_URL).origin;
const SHORTCUT = "CommandOrControl+Shift+Space";
const WIDTH = 380;
const HEIGHT = 580;

let win = null;
let tray = null;
app.isQuitting = false;

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on("second-instance", () => showWindow());
}

function placeWindow() {
  // top right, just under the menu bar, like a drop-down
  const { workArea } = screen.getPrimaryDisplay();
  win.setPosition(workArea.x + workArea.width - WIDTH - 16, workArea.y + 12);
}

function createWindow() {
  win = new BrowserWindow({
    width: WIDTH,
    height: HEIGHT,
    minWidth: 300,
    minHeight: 420,
    show: false,
    frame: false,
    fullscreenable: false,
    skipTaskbar: true,
    alwaysOnTop: true,
    backgroundColor: "#0a1d33",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      // a hidden window must keep polling for a check-in call, so never let it sleep
      backgroundThrottling: false,
      autoplayPolicy: "no-user-gesture-required",
    },
  });
  win.setAlwaysOnTop(true, "floating");
  win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  placeWindow();

  // closing hides it: the app lives in the menu bar
  win.on("close", (e) => {
    if (!app.isQuitting) {
      e.preventDefault();
      win.hide();
    }
  });

  // the frame is gone, so the header strip is the handle for dragging the window
  win.webContents.on("did-finish-load", () => {
    win.webContents.insertCSS("header{-webkit-app-region:drag} header button{-webkit-app-region:no-drag}");
  });
  // offline or the site is down: try again quietly
  win.webContents.on("did-fail-load", (_e, _code, _desc, _url, isMainFrame) => {
    if (isMainFrame) setTimeout(() => win && win.loadURL(APP_URL), 10000);
  });
  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });

  win.loadURL(APP_URL);
}

function showWindow() {
  if (!win) return;
  if (!win.isVisible()) win.showInactive(); // do not take the keyboard from whatever the person is doing
}

function toggleWindow() {
  if (!win) return;
  if (win.isVisible()) win.hide();
  else {
    placeWindow();
    win.show();
  }
}

function allowMicrophoneForOurSite() {
  const ses = session.defaultSession;
  ses.setPermissionRequestHandler((wc, permission, callback) => {
    let ok = false;
    try {
      ok = permission === "media" && new URL(wc.getURL()).origin === ORIGIN;
    } catch {
      /* a page with no address yet */
    }
    callback(ok);
  });
  ses.setPermissionCheckHandler((_wc, permission, origin) => permission === "media" && String(origin).startsWith(ORIGIN));
}

function buildMenu() {
  return Menu.buildFromTemplate([
    { label: "Show or hide", click: toggleWindow },
    {
      label: "Talk",
      accelerator: SHORTCUT,
      registerAccelerator: false, // the global shortcut is registered separately
      click: () => talk(),
    },
    { type: "separator" },
    {
      label: "Open at login",
      type: "checkbox",
      checked: app.getLoginItemSettings().openAtLogin,
      click: (item) => app.setLoginItemSettings({ openAtLogin: item.checked }),
    },
    { type: "separator" },
    {
      label: "Quit Memory Lane",
      click: () => {
        app.isQuitting = true;
        app.quit();
      },
    },
  ]);
}

function talk() {
  showWindow();
  if (win) win.webContents.send("talk-toggle");
}

function createTray() {
  const img = nativeImage.createFromPath(path.join(__dirname, "assets", "trayTemplate.png"));
  img.setTemplateImage(true);
  tray = new Tray(img);
  tray.setToolTip("Memory Lane");
  tray.on("click", toggleWindow);
  tray.on("right-click", () => tray.popUpContextMenu(buildMenu()));
}

// Start at login the first time the packaged app runs. The menu has the switch to turn it off.
function defaultToLogin() {
  if (!app.isPackaged) return;
  const flag = path.join(app.getPath("userData"), "first-run-done");
  if (fs.existsSync(flag)) return;
  app.setLoginItemSettings({ openAtLogin: true });
  fs.writeFileSync(flag, "1");
}

ipcMain.on("surface", () => showWindow()); // the companion is calling: bring the window up
ipcMain.on("mic", (_e, open) => {
  // a dot beside the menu bar icon is the privacy indicator: it shows only while the mic is open
  if (tray) tray.setTitle(open ? " ●" : "");
});

app.whenReady().then(async () => {
  if (process.platform === "darwin") app.dock.hide();
  allowMicrophoneForOurSite();
  createWindow();
  createTray();
  defaultToLogin();
  if (!globalShortcut.register(SHORTCUT, talk)) console.warn("could not register", SHORTCUT);
  if (process.platform === "darwin") {
    try {
      await systemPreferences.askForMediaAccess("microphone");
    } catch {
      /* the page asks again when it starts a call */
    }
  }
  win.once("ready-to-show", () => win.show());
});

app.on("before-quit", () => {
  app.isQuitting = true;
});
app.on("will-quit", () => globalShortcut.unregisterAll());
app.on("window-all-closed", () => {
  /* a menu bar app keeps running with no window */
});
