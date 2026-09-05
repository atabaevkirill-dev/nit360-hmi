const { app, BrowserWindow, ipcMain, shell } = require('electron');
const path = require('path');
const { startService } = require('./serial-service');

const IO_PORT = Number(process.env.NIT360_IO_PORT) || 3003;

let service = null;
let mainWindow = null;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1100,
    minHeight: 720,
    title: 'NIT-360 HMI | Тепловизор',
    backgroundColor: '#070b11',
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.once('ready-to-show', () => mainWindow.show());

  // Интерфейс — статические файлы в renderer/, сборка не требуется.
  // NIT360_UI_URL позволяет подменить его на dev-сервер при отладке.
  if (process.env.NIT360_UI_URL) {
    mainWindow.loadURL(process.env.NIT360_UI_URL);
  } else {
    mainWindow.loadFile(path.join(__dirname, '..', 'renderer', 'index.html'), {
      query: { ioPort: String(IO_PORT) },
    });
  }

  if (process.env.NIT360_DEVTOOLS === '1') {
    mainWindow.webContents.openDevTools({ mode: 'detach' });
  }

  // Внешние ссылки — в системном браузере, не в окне приложения.
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

ipcMain.handle('get-app-version', () => app.getVersion());
ipcMain.handle('get-io-port', () => IO_PORT);

app.whenReady().then(() => {
  service = startService({ port: IO_PORT });
  console.log(`[NIT-360] Сервис RS-422 слушает порт ${IO_PORT}`);

  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', async () => {
  if (service) {
    await service.stop();
    service = null;
  }
  if (process.platform !== 'darwin') app.quit();
});
