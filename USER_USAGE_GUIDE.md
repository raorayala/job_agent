# User Usage Guide — Local AI Job Search Agent

A private, local-first personal career assistant.

---

## Quick Reference Workflow

```powershell
# 1. Start local capture server for 1-click Chrome bookmarklet
python -m job_agent serve

# 2. Open automated search query links tailored to your config.yaml skills
python -m job_agent search-links --open

# 3. Direct search and fetch from job platforms (Dice, etc.)
python -m job_agent fetch-jobs --platforms dice

# 4. Re-score all jobs against your master resume text and profile
python -m job_agent analyze

# 5. List high-matching opportunities
python -m job_agent jobs --min-score 60

# 6. Generate ATS tailored DOCX resume & cover letter
python -m job_agent tailor <job_id>

# 7. Mark as applied after manual submission
python -m job_agent mark-applied <job_id> --confirm

# 8. View search pipeline dashboard
python -m job_agent dashboard
```

---

## 1-Click Chrome Bookmarklet Setup

1. Run `python -m job_agent serve` in terminal.
2. In Google Chrome, press `Ctrl + Shift + B` to show Bookmarks Bar.
3. Right-click Bookmarks Bar -> **Add page...**
   - **Name**: `Capture Job`
   - **URL**:
```javascript
javascript:(function(){
  const title = document.querySelector('h1')?.innerText || document.title;
  const company = document.querySelector('[data-testid="inlineHeader-companyName"], .companyName, .company-name, [data-cy="search-result-company-name"]')?.innerText || "Unknown";
  const url = window.location.href;
  const description = document.querySelector('#jobDescriptionText, .job-description, .description, #job-description')?.innerText || document.body.innerText.slice(0, 3000);

  fetch('http://localhost:8000/capture', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({title, company, url, description})
  })
  .then(res => res.json())
  .then(data => alert(`✅ Job Saved to Job Agent!\n\nID: #${data.job_id}\nTitle: ${data.title}\nCompany: ${data.company}\nMatch Score: ${data.score}/100`))
  .catch(err => alert('❌ Error: Make sure "python -m job_agent serve" is running in terminal.'));
})();
```
4. Click **`Capture Job`** on Chrome's bar while viewing any job on Indeed, Dice, ZipRecruiter, or Glassdoor!

---

## CLI Command Cheat Sheet

| Task | Command |
| :--- | :--- |
| **Verify Setup** | `python -m job_agent setup` |
| **Inspect Profile** | `python -m job_agent profile` |
| **Capture Server** | `python -m job_agent serve` |
| **Search Links** | `python -m job_agent search-links [--open]` |
| **Fetch Jobs** | `python -m job_agent fetch-jobs [--platforms dice]` |
| **Manual Add** | `python -m job_agent add-job --url URL --title T --company C` |
| **Gmail Sync** | `python -m job_agent sync-gmail` |
| **Analyze Scores**| `python -m job_agent analyze` |
| **List Jobs** | `python -m job_agent jobs [--min-score 60]` |
| **Tailor Resume** | `python -m job_agent tailor <job_id>` |
| **Mark Applied** | `python -m job_agent mark-applied <job_id> --confirm` |
| **Add Contact** | `python -m job_agent add-contact "Name" --job-id ID` |
| **List Contacts** | `python -m job_agent contacts` |
| **Add Interview** | `python -m job_agent add-interview ID "YYYY-MM-DD HH:MM"` |
| **Interview Prep**| `python -m job_agent prepare-interview ID` |
| **Answer Draft** | `python -m job_agent suggest-answer ID "Question"` |
| **Dashboard** | `python -m job_agent dashboard` |
| **Weekly Report** | `python -m job_agent report --period weekly` |
| **Local Backup** | `python -m job_agent backup` |
| **Restore Backup**| `python -m job_agent restore PATH` |
