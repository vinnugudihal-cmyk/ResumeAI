const express = require('express')
const cors = require('cors')
const multer = require('multer')
const path = require('path')
const fs = require('fs')
const crypto = require('crypto')
const axios = require('axios')
const FormData = require('form-data')

const app = express()
const PORT = 5000

// The Python AI service owns the SQLite database. This backend
// is a thin proxy so there is exactly one database and one
// source of truth for analyses.
const AI_SERVICE_URL = process.env.AI_SERVICE_URL || 'http://127.0.0.1:8000'

const UPLOAD_DIR = path.resolve(__dirname, 'uploads')
const MAX_FILE_BYTES = 5 * 1024 * 1024
const ALLOWED_EXTENSIONS = ['.pdf']

// Credentials must be allowed: otherwise the browser silently
// discards the session cookie this proxy relays, and sign-in
// fails whenever the frontend falls back to this port.
app.use(cors({ origin: true, credentials: true }))
app.use(express.json())

if (!fs.existsSync(UPLOAD_DIR)) {
  fs.mkdirSync(UPLOAD_DIR, { recursive: true })
}

/* ============================================================
   UPLOAD SECURITY
   ============================================================ */

const storage = multer.diskStorage({
  destination: (req, file, cb) => {
    cb(null, UPLOAD_DIR)
  },
  filename: (req, file, cb) => {
    // Never trust the client filename for the stored name.
    const ext = path.extname(file.originalname || '').toLowerCase()
    const safeExt = ALLOWED_EXTENSIONS.includes(ext) ? ext : '.pdf'
    const uniqueName = `${Date.now()}-${crypto.randomUUID()}${safeExt}`
    cb(null, uniqueName)
  },
})

function fileFilter(req, file, cb) {
  const ext = path.extname(file.originalname || '').toLowerCase()

  if (!ALLOWED_EXTENSIONS.includes(ext)) {
    return cb(
      new Error('Only PDF resume files are supported.')
    )
  }

  cb(null, true)
}

const upload = multer({
  storage,
  fileFilter,
  limits: { fileSize: MAX_FILE_BYTES, files: 1 },
})

/* ============================================================
   HELPERS
   ============================================================ */

/**
 * Forward the browser's session cookie to the AI service and
 * copy the resulting Set-Cookie back. This is what keeps the
 * Flask session alive when requests go through this proxy.
 */
function withSession(req) {
  return req.headers.cookie
    ? { Cookie: req.headers.cookie }
    : {};
}

function relayCookies(res, upstream) {
  const raw = upstream?.headers?.['set-cookie'];

  if (!raw) return;

  const list = Array.isArray(raw) ? raw : [raw];

  for (const cookie of list) {
    res.append('Set-Cookie', cookie);
  }
}

async function proxyJson(req, res, path, method = 'GET', data = null) {
  try {
    const config = {
      method,
      url: `${AI_SERVICE_URL}${path}`,
      headers: withSession(req),
      timeout: 20000,
    };

    if (data !== null) {
      config.data = data;
    }

    const upstream = await axios(config);

    relayCookies(res, upstream);

    res.status(upstream.status).json(upstream.data);
  } catch (error) {
    const status = error.response?.status || 500;

    if (error.response?.headers?.['set-cookie']) {
      relayCookies(res, error.response);
    }

    res.status(status).json({
      error:
        error.response?.data?.error ||
        'Could not reach the ResumeAI AI service.',
    });
  }
}

function isPdf(buffer) {
  return buffer && buffer.length > 4 &&
    buffer.slice(0, 4).toString('binary') === '%PDF'
}

function removeFile(filePath) {
  try {
    if (filePath && fs.existsSync(filePath)) {
      fs.unlinkSync(filePath)
    }
  } catch (error) {
    console.warn('Could not remove upload:', error.message)
  }
}

function cleanUpload(req) {
  if (req.file && req.file.path) {
    removeFile(req.file.path)
  }
}

/* ============================================================
   ROUTES
   ============================================================ */

app.get('/', (req, res) => {
  res.json({
    message: 'ResumeAI backend is running!',
  })
})

app.get('/api/health', async (req, res) => {
  try {
    const aiResponse = await axios.get(
      `${AI_SERVICE_URL}/health`,
      { timeout: 8000 }
    )

    res.json({
      status: 'ok',
      service: 'resumeai-backend',
      ai_service: aiResponse.data,
    })
  } catch (error) {
    res.status(503).json({
      status: 'degraded',
      service: 'resumeai-backend',
      error: 'AI service is not reachable.',
    })
  }
})

app.post('/api/resume/upload', (req, res) => {
  upload.single('resume')(req, res, async (uploadError) => {
    if (uploadError) {
      if (uploadError.code === 'LIMIT_FILE_SIZE') {
        return res.status(413).json({
          message: 'Resume file is too large. Maximum size is 5MB.',
        })
      }

      return res.status(400).json({
        message: uploadError.message || 'Invalid file upload.',
      })
    }

    if (!req.file) {
      return res.status(400).json({
        message: 'Please upload a resume',
      })
    }

    try {
      // Verify the bytes really are a PDF.
      const head = Buffer.alloc(5)
      const fd = fs.openSync(req.file.path, 'r')
      fs.readSync(fd, head, 0, 5, 0)
      fs.closeSync(fd)

      if (!isPdf(head)) {
        cleanUpload(req)
        return res.status(400).json({
          message: 'That file is not a valid PDF.',
        })
      }

      const formData = new FormData()

      formData.append(
        'resume',
        fs.createReadStream(req.file.path)
      )

      const jobDescription = (
        req.body?.job_description ||
        req.body?.jobDescription ||
        ''
      ).toString().trim().slice(0, 20000)

      if (jobDescription) {
        formData.append('job_description', jobDescription)
      }

      // Pass the readable name for history. The AI service
      // sanitises it again and keeps the random on-disk name
      // for the file itself.
      formData.append(
        'original_filename',
        req.file.originalname || 'resume.pdf'
      )

      const aiResponse = await axios.post(
        `${AI_SERVICE_URL}/analyze`,
        formData,
        {
          headers: {
            ...formData.getHeaders(),
            ...withSession(req),
          },
          maxBodyLength: MAX_FILE_BYTES * 2,
          timeout: 120000,
        }
      )

      relayCookies(res, aiResponse)

      res.json({
        message: 'Resume analyzed successfully',
        filename: req.file.filename,
        originalName: req.file.originalname,
        analysis: aiResponse.data,
      })
    } catch (error) {
      cleanUpload(req)

      const status = error.response?.status || 500

      if (error.response?.headers?.['set-cookie']) {
        relayCookies(res, error.response)
      }

      // Pass the AI service's own message through when it has one.
      const message =
        error.response?.data?.error ||
        (status === 500
          ? 'AI analysis failed'
          : error.message)

      if (status >= 500) {
        console.error(error.message)
      }

      res.status(status).json({
        message,
        error: error.message,
      })
    }
  })
})

// ---- Authentication (proxied; session cookie is forwarded) ----

app.post('/api/auth/register', (req, res) =>
  proxyJson(req, res, '/auth/register', 'POST', req.body)
)

app.post('/api/auth/login', (req, res) =>
  proxyJson(req, res, '/auth/login', 'POST', req.body)
)

app.post('/api/auth/logout', (req, res) =>
  proxyJson(req, res, '/auth/logout', 'POST', {})
)

app.get('/api/auth/me', (req, res) =>
  proxyJson(req, res, '/auth/me')
)

// ---- Analysis history (proxied to the single database) ----

app.get('/api/analyses', (req, res) => {
  const params = {}

  if (req.query.limit !== undefined) {
    params.limit = req.query.limit
  }

  if (req.query.offset !== undefined) {
    params.offset = req.query.offset
  }

  const query = new URLSearchParams(params).toString()

  proxyJson(req, res, `/analyses${query ? `?${query}` : ''}`)
})

app.get('/api/analyses/:id', (req, res) =>
  proxyJson(req, res, `/analyses/${encodeURIComponent(req.params.id)}`)
)

app.delete('/api/analyses/:id', (req, res) =>
  proxyJson(
    req,
    res,
    `/analyses/${encodeURIComponent(req.params.id)}`,
    'DELETE'
  )
)

// Anything else
app.use((req, res) => {
  res.status(404).json({ error: 'Endpoint not found.' })
})

// Never let an unexpected error kill the process
app.use((error, req, res, next) => {
  console.error(error.message)
  res.status(500).json({ error: 'Internal server error.' })
})

app.listen(PORT, () => {
  console.log(`ResumeAI backend running on http://localhost:${PORT}`)
  console.log(`Proxying analysis + history to ${AI_SERVICE_URL}`)
})
