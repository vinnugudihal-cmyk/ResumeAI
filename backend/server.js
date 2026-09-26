const express = require('express')
const cors = require('cors')
const multer = require('multer')
const path = require('path')
const fs = require('fs')
const axios = require('axios')
const FormData = require('form-data')

const app = express()
const PORT = 5000

app.use(cors())
app.use(express.json())

const storage = multer.diskStorage({
  destination: (req, file, cb) => {
    cb(null, 'uploads/')
  },
  filename: (req, file, cb) => {
    const uniqueName = Date.now() + '-' + file.originalname
    cb(null, uniqueName)
  },
})

const upload = multer({ storage })

app.get('/', (req, res) => {
  res.json({
    message: 'ResumeAI backend is running!',
  })
})

app.post('/api/resume/upload', upload.single('resume'), async (req, res) => {
  if (!req.file) {
    return res.status(400).json({
      message: 'Please upload a resume',
    })
  }

  try {
    const formData = new FormData()

    formData.append(
      'resume',
      fs.createReadStream(path.resolve(req.file.path))
    )

    const jobDescription = (
      req.body?.job_description ||
      req.body?.jobDescription ||
      ''
    ).toString().trim().slice(0, 20000)

    if (jobDescription) {
      formData.append('job_description', jobDescription)
    }

    const aiResponse = await axios.post(
      'http://127.0.0.1:8000/analyze',
      formData,
      {
        headers: formData.getHeaders(),
      }
    )

    res.json({
      message: 'Resume analyzed successfully',
      filename: req.file.filename,
      originalName: req.file.originalname,
      analysis: aiResponse.data,
    })
  } catch (error) {
    console.error(error.message)

    res.status(500).json({
      message: 'AI analysis failed',
      error: error.message,
    })
  }
})

app.listen(PORT, () => {
  console.log(`ResumeAI backend running on http://localhost:${PORT}`)
})