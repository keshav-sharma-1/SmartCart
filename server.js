const express = require('express');
const { spawn } = require('child_process');
const path = require('path');
const cors = require('cors');
const winston = require('winston');
const DailyRotateFile = require('winston-daily-rotate-file');
const morgan = require('morgan');
const fs = require('fs');

// Create logs directory if it doesn't exist
const logsDir = path.join(__dirname, 'logs');
if (!fs.existsSync(logsDir)) {
    fs.mkdirSync(logsDir);
    console.log('Created logs directory');
}

// ---------------- Winston Logger (single combined file) ----------------
const logger = winston.createLogger({
    level: process.env.LOG_LEVEL || 'debug',
    format: winston.format.combine(
        winston.format.timestamp({ format: 'YYYY-MM-DD HH:mm:ss.SSS' }),
        winston.format.printf(({ level, message, timestamp, requestId }) => {
            return `${timestamp} ${level.toUpperCase()} ${requestId || '-'} ${message}`;
        })
    ),
    transports: [
        new winston.transports.Console({
            format: winston.format.combine(
                winston.format.colorize(),
                winston.format.timestamp({ format: 'YYYY-MM-DD HH:mm:ss.SSS' }),
                winston.format.printf(({ level, message, timestamp, requestId }) => {
                    return `${timestamp} ${level.toUpperCase()} ${requestId || '-'} ${message}`;
                })
            )
        }),
        new DailyRotateFile({
            filename: path.join(logsDir, 'server-%DATE%.log'),
            datePattern: 'YYYY-MM-DD',
            maxSize: '50m',
            maxFiles: '5d'
        })
    ]
});

// ---------------- Request ID Generator ----------------
let requestCounter = 0;
const generateRequestId = () => {
    requestCounter = (requestCounter + 1) % 1000000;
    return `req_${Date.now()}_${requestCounter}`;
};

// ---------------- Express App ----------------
const app = express();
const PORT = process.env.PORT || 8080;

logger.info('Starting Product Search & Comparison Server', {
    port: PORT,
    nodeEnv: process.env.NODE_ENV || 'development',
    nodeVersion: process.version,
    platform: process.platform
});

// Morgan logging with request IDs
morgan.token('id', (req) => req.id);
morgan.token('user-agent', (req) => req.get('user-agent'));
app.use((req, res, next) => {
    req.id = generateRequestId();
    req.startTime = Date.now();
    next();
});
app.use(morgan(':id :method :url :status :res[content-length] - :response-time ms ":user-agent"', {
    stream: {
        write: (message) => logger.info(message.trim(), { requestId: '-' })
    }
}));

app.use(express.json({ limit: '10mb' }));
app.use(cors({ origin: process.env.CORS_ORIGIN || true, credentials: true }));

// ----------------- Routes -----------------
app.get('/', (req, res) => {
    const htmlPath = path.join(__dirname, 'public', 'index.html');
    if (!fs.existsSync(htmlPath)) {
        return res.status(404).json({ error: 'HTML file not found' });
    }
    res.sendFile(htmlPath);
});

app.post('/api/search', async (req, res) => {
    const requestId = req.id;
    deleteJsonFiles('./');
    try {

        const { query } = req.body;
         logger.info(`Search input is : ${query}`, { requestId });

        if (!query || typeof query !== 'string' || query.trim().length === 0) {
            return res.status(400).json({
                error: 'Query parameter is required and must be a non-empty string',
                requestId
            });
        }

        const parsedData = await callPythonScript(query, requestId);

        res.json({
            success: true,
            query,
            data: parsedData,
            count: Array.isArray(parsedData) ? parsedData.length : 1,
            requestId,
            timestamp: new Date().toISOString()
        });

    } catch (error) {
        logger.error(`Search request failed: ${error.message}`, { requestId });
        res.status(500).json({
            error: 'Internal server error occurred during search',
            details: process.env.NODE_ENV === 'development' ? error.message : undefined,
            requestId,
            timestamp: new Date().toISOString()
        });
    }
});

app.get('/health', (req, res) => {
    const requestId = req.id;
    res.json({
        status: 'OK',
        timestamp: new Date().toISOString(),
        uptime: process.uptime(),
        memory: process.memoryUsage(),
        pid: process.pid,
        version: {
            node: process.version,
            app: require('./package.json').version
        },
        environment: process.env.NODE_ENV || 'development',
        requestId
    });
});

app.use('*', (req, res) => {
    res.status(404).json({
        error: 'Route not found',
        method: req.method,
        url: req.url,
        requestId: req.id,
        timestamp: new Date().toISOString()
    });
});

// ----------------- Python Script Handler -----------------
function callPythonScript(query, requestId) {
    return new Promise((resolve, reject) => {
        const pythonScript = path.join(__dirname, 'scripts', 'main-pro.py');
        const outputFile = path.join(__dirname, 'output.json');

        if (!fs.existsSync(pythonScript)) {
            return reject(new Error(`Python script not found at: ${pythonScript}`));
        }

        if (fs.existsSync(outputFile)) {
            fs.unlinkSync(outputFile);
        }

        const pythonProcess = spawn('python3', [pythonScript, '--product', query], {
            env: { ...process.env, REQUEST_ID: requestId }
        });



        pythonProcess.stdout.on('data', (data) => {
            logger.info(`PYTHON LOG: ${data.toString().trim()}`);
        });

        let errorString = '';

        pythonProcess.stderr.on('data', (data) => {
            errorString += data.toString();
        });

        pythonProcess.on('close', (code) => {
            if (code === 0) {
                try {
                    if (!fs.existsSync(outputFile)) {
                        return reject(new Error('Python script completed but no output.json found'));
                    }
                    const fileData = fs.readFileSync(outputFile, 'utf-8');
                    const jsonData = JSON.parse(fileData);
                    resolve(jsonData);
                } catch (err) {
                    reject(new Error(`Failed to read/parse output.json: ${err.message}`));
                }
            } else {
                reject(new Error(`Python script exited with code ${code}: ${errorString}`));
            }
        });

        pythonProcess.on('error', (err) => {
            reject(new Error(`Failed to start Python script: ${err.message}`));
        });

        setTimeout(() => {
            pythonProcess.kill('SIGKILL');
            reject(new Error('Python script timeout after 5 minutes'));
        }, 5 * 60 * 1000);
    });
}

function deleteJsonFiles(directory) {
  const files = fs.readdirSync(directory);

  files.forEach(file => {
    if (/^results.*\.json$/.test(file) || file === 'output.json') {
      const filePath = path.join(directory, file);
      try {
        fs.unlinkSync(filePath);
        console.log(`Deleted: ${file}`);
      } catch (err) {
        console.error(`Error deleting ${file}:`, err);
      }
    }
  });
}

// ----------------- Start Server -----------------
const server = app.listen(PORT, '0.0.0.0',() => {
    console.log(`🚀 Server running on http://localhost:${PORT}`);
    deleteJsonFiles('./');
});


// ----------------- Graceful Shutdown -----------------
const gracefulShutdown = (signal) => {
    logger.info(`Received ${signal}, shutting down...`);
    server.close(() => process.exit(0));
};
process.on('SIGTERM', () => gracefulShutdown('SIGTERM'));
process.on('SIGINT', () => gracefulShutdown('SIGINT'));
