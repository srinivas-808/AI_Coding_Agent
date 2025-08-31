// backend/static/script.js

const API_BASE_URL = ''; // Flask serves from the same origin, so relative path is fine
const POLLING_INTERVAL = 3000; // Poll every 3 seconds

// DOM Elements
const challengeForm = document.getElementById('challenge-form');
const rawInputDiv = document.getElementById('natural-lang-input');
const structuredJsonDiv = document.getElementById('structured-json-input');
const btnNaturalLang = document.getElementById('btn-natural-lang');
const btnStructuredJson = document.getElementById('btn-structured-json');
const rawInput = document.getElementById('rawInput');
const structuredDescription = document.getElementById('structuredDescription');
const structuredTestCases = document.getElementById('structuredTestCases');
const maxAttemptsInput = document.getElementById('maxAttempts');
const formError = document.getElementById('form-error');
const submitBtn = document.getElementById('submit-btn');

const statusContent = document.getElementById('status-content');
const resetChallengeContainer = document.getElementById('reset-challenge-container');
const resetChallengeBtn = document.getElementById('reset-challenge-btn');

const toggleSolvedChallengesBtn = document.getElementById('toggle-solved-challenges-btn');
const solvedChallengesSection = document.getElementById('solved-challenges-section');
const solvedListDiv = document.getElementById('solved-list');
const paginationControls = document.getElementById('pagination-controls');
const prevPageBtn = document.getElementById('prev-page-btn');
const nextPageBtn = document.getElementById('next-page-btn');
const pageInfoSpan = document.getElementById('page-info');


let currentInputMode = 'natural'; // 'natural' or 'structured'
let currentChallengeId = null;
let pollingIntervalId = null;
let solvedChallengesData = []; // Store all fetched solved challenges
let currentPage = 1; // Current page for pagination
const itemsPerPage = 5; // Number of solved challenges to display per page

// --- Utility Functions ---
function showFormError(message) {
    formError.textContent = message;
    formError.classList.remove('hidden');
}

function hideFormError() {
    formError.classList.add('hidden');
    formError.textContent = '';
}

function setLoadingState(isLoading) {
    submitBtn.disabled = isLoading;
    submitBtn.textContent = isLoading ? 'Submitting...' : 'Solve Challenge';
    if (isLoading) {
        submitBtn.classList.add('opacity-50', 'cursor-not-allowed');
    } else {
        submitBtn.classList.remove('opacity-50', 'cursor-not-allowed');
    }
}

function stripExcessComments(code) {
    // Remove single-line comments starting with #
    let cleanedCode = code.split('\n')
        .filter(line => !line.trim().startsWith('#'))
        .join('\n');

    // Remove multi-line comments/docstrings (triple quotes)
    // This regex is a bit aggressive and might remove valid multi-line strings
    // if they are not part of code logic. For "minimal and only necessary",
    // this is a reasonable interpretation.
    cleanedCode = cleanedCode.replace(/("""[^"]*"""|'''[^']*''')/gs, (match, p1) => {
        // Check if the match is a standalone docstring at the start of a line or after indentation
        const lines = p1.trim().split('\n');
        if (lines.length > 1 || (lines.length === 1 && (match.trim().startsWith('"""') || match.trim().startsWith("'''")) && match.trim().endsWith('"""') || match.trim().endsWith("'''"))) {
            return ''; // Remove the entire block
        }
        return match; // Keep if it's a single-line string literal within code
    });

    // Remove empty lines that might result from comment stripping
    cleanedCode = cleanedCode.split('\n').filter(line => line.trim() !== '').join('\n');

    return cleanedCode.trim();
}

// Global function to copy text to clipboard
window.copyToClipboard = function (text) {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    document.body.appendChild(textarea);
    textarea.select();
    try {
        document.execCommand('copy');
        alert('Code copied to clipboard!'); // Use a custom modal in a real app
    } catch (err) {
        console.error('Failed to copy text: ', err);
        alert('Failed to copy code.');
    }
    document.body.removeChild(textarea);
};


function renderStatusContent(status, data, solutionCode, error) {
    let html = '';
    if (error) {
        html = `<p class="text-red-600 text-center font-medium mb-4">${error}</p>`;
    } else if (status === 'idle') {
        html = `<p class="text-gray-600 text-center">Submit a challenge to see its status here.</p>`;
    } else if (data) {
        let statusBadgeClass = 'bg-gray-400';
        let statusText = 'Unknown';
        if (status === 'processing') { statusBadgeClass = 'bg-yellow-500'; statusText = 'Processing...'; }
        else if (status === 'solved') { statusBadgeClass = 'bg-green-600'; statusText = 'Solved! 🎉'; statusText = 'Solved! 🎉'; }
        else if (status === 'failed') { statusBadgeClass = 'bg-red-600'; statusText = 'Failed ❌'; }
        else if (status === 'error') { statusBadgeClass = 'bg-red-700'; statusText = 'Error! 🛑'; }
        else if (status === 'loading') { statusBadgeClass = 'bg-blue-500'; statusText = 'Loading...'; }

        html = `
            <div class="space-y-4">
                <p class="flex justify-between items-center text-gray-700">
                    <span class="font-semibold">Challenge ID:</span> 
                    <span class="font-mono bg-gray-100 p-1 rounded text-sm">${data.challenge_id}</span>
                </p>
                <p class="flex justify-between items-center text-gray-700">
                    <span class="font-semibold">Status:</span> 
                    <span class="inline-block px-3 py-1 rounded-full text-white text-sm font-semibold ${statusBadgeClass}">
                        ${statusText}
                    </span>
                </p>
                <p class="text-gray-700">
                    <span class="font-semibold">Description:</span> ${data.description || 'N/A'}
                </p>
        `;

        if (status === 'solved' || status === 'failed' || status === 'error') {
            const cleanedSolutionCode = stripExcessComments(solutionCode); // Clean comments
            html += `
                <div class="mt-4 p-4 border border-green-300 bg-green-50 rounded-lg shadow-inner">
                    <h3 class="text-xl font-bold mb-2 text-green-800 flex justify-between items-center">
                        Solution Code
                        <button onclick="copyToClipboard(decodeURIComponent('${encodeURIComponent(cleanedSolutionCode)}'))" 
                                class="px-3 py-1 bg-blue-500 text-white text-sm rounded-md hover:bg-blue-600 transition-colors duration-200">
                            Copy Code
                        </button>
                    </h3>
                    <pre class="bg-gray-800 text-white p-4 rounded-md overflow-x-auto text-sm font-mono">
                        <code>${cleanedSolutionCode || 'No code available.'}</code>
                    </pre>
                </div>
            `;
            if (data.result && data.result.error_details) {
                const errorDetails = data.result.error_details;
                html += `
                    <div class="mt-4 p-3 bg-red-100 border border-red-400 text-red-700 rounded-md">
                        <h4 class="font-semibold">Error Details:</h4>
                        <p><strong>Message:</strong> ${errorDetails.message || 'N/A'}</p>
                        <p><strong>Type:</strong> ${errorDetails.exception_type || 'N/A'}</p>
                        ${errorDetails.error_message ? `<p><strong>Backend Error:</strong> ${errorDetails.error_message}</p>` : ''}
                `;
                if (errorDetails.test_results && errorDetails.test_results.length > 0) {
                    const failingTests = errorDetails.test_results.filter(t => !t.passed);
                    if (failingTests.length > 0) {
                        html += `<h5 class="font-semibold mt-2">Failing Tests:</h5><ul class="list-disc list-inside text-sm">`;
                        failingTests.forEach((test, index) => {
                            html += `<li>Input: ${JSON.stringify(test.input)}, Expected: ${JSON.stringify(test.expected_output)}, Actual: ${JSON.stringify(test.actual_output)}`;
                            if (test.error) html += `<span class="text-red-500"> (Error: ${test.error})</span>`;
                            html += `</li>`;
                        });
                        html += `</ul>`;
                    }
                }
                html += `</div>`; // Close error_details div
            }
        } else {
            html += `<p class="text-gray-600 italic mt-4">Waiting for agent to process and debug...</p>`;
        }
        html += `</div>`; // Close space-y-4 div
    } else {
        html = `<p class="text-gray-600 text-center">Fetching challenge status...</p>`;
    }
    statusContent.innerHTML = html;

    // Show/hide reset button
    if (currentChallengeId) {
        resetChallengeContainer.classList.remove('hidden');
    } else {
        resetChallengeContainer.classList.add('hidden');
    }
}

async function fetchChallengeStatus() {
    if (!currentChallengeId) {
        renderStatusContent('idle', null, '', '');
        return;
    }

    try {
        const response = await fetch(`${API_BASE_URL}/challenge_status/${currentChallengeId}`);
        const data = await response.json();

        const status = data.status;
        // Correctly extract solutionCode from data.solution or data.result
        const solutionCode = data.solution?.final_code || data.result?.final_code || '';
        const error = data.error || data.result?.message || '';

        renderStatusContent(status, data, solutionCode, error);

        const isTerminalState = ['solved', 'failed', 'error'].includes(status);
        if (isTerminalState) {
            clearInterval(pollingIntervalId);
            pollingIntervalId = null;
            console.log(`Polling stopped for challenge ${currentChallengeId} (Status: ${status})`);
            if (status === 'solved') {
                // Always refresh solved list when a challenge is solved
                fetchSolvedChallenges();
            }
        }
    } catch (err) {
        console.error('Error fetching challenge status:', err);
        renderStatusContent('error', null, '', 'Failed to fetch challenge status. Check backend.');
        clearInterval(pollingIntervalId);
        pollingIntervalId = null;
    }
}

async function fetchSolvedChallenges() {
    solvedListDiv.innerHTML = '<p class="text-gray-600 text-center">Loading solved challenges...</p>';
    paginationControls.classList.add('hidden'); // Hide pagination while loading
    try {
        const response = await fetch(`${API_BASE_URL}/solved_challenges`);
        const allSolvedChallenges = await response.json();

        // Sort by solved_timestamp in descending order (most recent first)
        solvedChallengesData = allSolvedChallenges.sort((a, b) =>
            new Date(b.solved_timestamp) - new Date(a.solved_timestamp)
        );

        currentPage = 1; // Reset to first page on new fetch
        renderSolvedChallenges(); // Render the challenges with current limit

    } catch (err) {
        console.error('Error fetching solved challenges:', err);
        solvedListDiv.innerHTML = '<p class="text-red-600 text-center">Failed to load solved challenges.</p>';
    }
}

function renderSolvedChallenges() {
    if (solvedChallengesData.length === 0) {
        solvedListDiv.innerHTML = '<p class="text-gray-600 text-center">No challenges solved yet. Submit one!</p>';
        paginationControls.classList.add('hidden');
        return;
    }

    let html = '';
    const totalPages = Math.ceil(solvedChallengesData.length / itemsPerPage);
    const startIndex = (currentPage - 1) * itemsPerPage;
    const endIndex = startIndex + itemsPerPage;
    const challengesToDisplay = solvedChallengesData.slice(startIndex, endIndex);

    challengesToDisplay.forEach((challenge, index) => {
        const descriptionSnippet = challenge.challenge_description.substring(0, 80) + (challenge.challenge_description.length > 80 ? '...' : '');
        const solvedDate = new Date(challenge.solved_timestamp).toLocaleString();
        
        const codeId = `solved-code-${startIndex + index}`; // Unique ID for each item
        const testId = `solved-tests-${startIndex + index}`;
        const cleanedFinalCode = stripExcessComments(challenge.final_code); // Clean comments here

        html += `
            <div class="border border-gray-200 rounded-md p-4 bg-gray-50 hover:bg-gray-100 transition-colors duration-150">
                <h3 class="text-lg font-semibold text-gray-800 mb-2">${descriptionSnippet}</h3>
                <p class="text-sm text-gray-600 mb-1">
                    <span class="font-medium">Language:</span> ${challenge.language || 'python'}
                </p>
                <p class="text-sm text-gray-600 mb-1">
                    <span class="font-medium">Attempts:</span> ${challenge.attempts_taken}
                </p>
                <p class="text-sm text-gray-600 mb-2">
                    <span class="font-medium">Solved On:</span> ${solvedDate}
                </p>
                
                <button
                    onclick="toggleVisibility('${codeId}', this)"
                    class="text-blue-600 hover:text-blue-800 text-sm font-medium focus:outline-none mr-4"
                >
                    Show Code
                </button>
                <button
                    onclick="toggleVisibility('${testId}', this)"
                    class="text-blue-600 hover:text-blue-800 text-sm font-medium focus:outline-none"
                >
                    Show Test Cases
                </button>

                <div id="${codeId}" class="mt-3 hidden">
                    <h4 class="text-md font-semibold text-gray-700 mb-1">Final Code:</h4>
                    <pre class="bg-gray-800 text-white p-3 rounded-md overflow-x-auto text-xs font-mono">
                        <code>${cleanedFinalCode}</code>
                    </pre>
                </div>
                <div id="${testId}" class="mt-3 hidden">
                    <h4 class="text-md font-semibold text-gray-700 mt-3 mb-1">Test Cases:</h4>
                    <pre class="bg-gray-100 text-gray-800 p-3 rounded-md overflow-x-auto text-xs font-mono">
                        <code>${JSON.stringify(challenge.test_cases, null, 2)}</code>
                    </pre>
                </div>
            </div>
        `;
    });
    solvedListDiv.innerHTML = html;

    // Update pagination controls
    if (totalPages > 1) {
        paginationControls.classList.remove('hidden');
        pageInfoSpan.textContent = `Page ${currentPage} of ${totalPages}`;
        prevPageBtn.disabled = currentPage === 1;
        nextPageBtn.disabled = currentPage === totalPages;
    } else {
        paginationControls.classList.add('hidden');
    }
}

function goToPreviousPage() {
    if (currentPage > 1) {
        currentPage--;
        renderSolvedChallenges();
        solvedListDiv.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
}

function goToNextPage() {
    const totalPages = Math.ceil(solvedChallengesData.length / itemsPerPage);
    if (currentPage < totalPages) {
        currentPage++;
        renderSolvedChallenges();
        solvedListDiv.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
}


// Global function for toggling visibility (needed because it's called from inline onclick)
window.toggleVisibility = function (elementId, buttonElement) {
    const element = document.getElementById(elementId);
    if (element) {
        element.classList.toggle('hidden');
        if (element.classList.contains('hidden')) {
            if (elementId.includes('code')) {
                buttonElement.textContent = 'Show Code';
            } else if (elementId.includes('test')) {
                buttonElement.textContent = 'Show Test Cases';
            }
        } else {
            if (elementId.includes('code')) {
                buttonElement.textContent = 'Hide Code';
            } else if (elementId.includes('test')) {
                buttonElement.textContent = 'Hide Test Cases';
            }
        }
    }
};


// --- Event Listeners ---
btnNaturalLang.addEventListener('click', () => {
    currentInputMode = 'natural';
    rawInputDiv.classList.remove('hidden');
    structuredJsonDiv.classList.add('hidden');
    btnNaturalLang.classList.add('bg-blue-600', 'text-white', 'shadow-lg');
    btnNaturalLang.classList.remove('bg-gray-200', 'text-gray-700', 'hover:bg-gray-300');
    btnStructuredJson.classList.remove('bg-blue-600', 'text-white', 'shadow-lg');
    btnStructuredJson.classList.add('bg-gray-200', 'text-gray-700', 'hover:bg-gray-300');
    hideFormError();
});

btnStructuredJson.addEventListener('click', () => {
    currentInputMode = 'structured';
    rawInputDiv.classList.add('hidden');
    structuredJsonDiv.classList.remove('hidden');
    btnStructuredJson.classList.add('bg-blue-600', 'text-white', 'shadow-lg');
    btnStructuredJson.classList.remove('bg-gray-200', 'text-gray-700', 'hover:bg-gray-300');
    btnNaturalLang.classList.remove('bg-blue-600', 'text-white', 'shadow-lg');
    btnNaturalLang.classList.add('bg-gray-200', 'text-gray-700', 'hover:bg-gray-300');
    hideFormError();
});

challengeForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    hideFormError();
    setLoadingState(true);

    let payload = { max_attempts: parseInt(maxAttemptsInput.value) };

    if (currentInputMode === 'natural') {
        if (!rawInput.value.trim()) {
            showFormError('Natural language input cannot be empty.');
            setLoadingState(false);
            return;
        }
        payload.raw_input = rawInput.value;
    } else { // structured mode
        if (!structuredDescription.value.trim()) {
            showFormError('Challenge Description cannot be empty.');
            setLoadingState(false);
            return;
        }
        if (!structuredTestCases.value.trim()) {
            showFormError('Test Cases JSON cannot be empty.');
            setLoadingState(false);
            return;
        }
        try {
            payload.description = structuredDescription.value;
            payload.test_cases = JSON.parse(structuredTestCases.value);
            // Basic validation for test cases
            if (!Array.isArray(payload.test_cases)) {
                throw new Error("Test cases must be a JSON array.");
            }
            for (const tc of payload.test_cases) {
                if (typeof tc !== 'object' || tc === null || !('input' in tc) || !('expected_output' in tc)) {
                    throw new Error("Each test case must be an object with 'input' and 'expected_output' keys.");
                }
            }
        } catch (jsonError) {
            showFormError(`Invalid JSON for test cases: ${jsonError.message}. Please check syntax.`);
            setLoadingState(false);
            return;
        }
    }

    try {
        const response = await fetch(`${API_BASE_URL}/submit_challenge`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await response.json();

        if (response.ok) {
            currentChallengeId = data.challenge_id;
            // Clear form fields
            rawInput.value = '';
            structuredDescription.value = '';
structuredTestCases.value = '';
            maxAttemptsInput.value = 5;
            
            // Start polling for status
            if (pollingIntervalId) clearInterval(pollingIntervalId); // Clear any old interval
            pollingIntervalId = setInterval(fetchChallengeStatus, POLLING_INTERVAL);
            fetchChallengeStatus(); // Initial fetch immediately
            
            document.getElementById('challenge-status-section')?.scrollIntoView({ behavior: 'smooth' });

        } else {
            showFormError(data.error || 'Failed to submit challenge. Check backend logs.');
        }
    } catch (err) {
        console.error('Error submitting challenge:', err);
        showFormError('Network error or backend is unreachable.');
    } finally {
        setLoadingState(false);
    }
});

resetChallengeBtn.addEventListener('click', () => {
    currentChallengeId = null;
    if (pollingIntervalId) {
        clearInterval(pollingIntervalId);
        pollingIntervalId = null;
    }
    renderStatusContent('idle', null, '', ''); // Reset status display
    // Reset solved challenges pagination
    currentPage = 1;
    // Always re-fetch solved challenges on reset, if the section is visible
    if (!solvedChallengesSection.classList.contains('hidden')) {
        fetchSolvedChallenges();
    }
    document.getElementById('submit-challenge-section')?.scrollIntoView({ behavior: 'smooth' });
});

toggleSolvedChallengesBtn.addEventListener('click', () => {
    solvedChallengesSection.classList.toggle('hidden');
    if (solvedChallengesSection.classList.contains('hidden')) {
        toggleSolvedChallengesBtn.textContent = 'Show Solved Challenges';
    } else {
        toggleSolvedChallengesBtn.textContent = 'Hide Solved Challenges';
        // If showing, ensure challenges are loaded/rendered
        if (solvedChallengesData.length === 0 || solvedListDiv.innerHTML.includes('Loading solved challenges')) {
            fetchSolvedChallenges();
        } else {
            renderSolvedChallenges(); // Just re-render if already fetched
        }
    }
});

prevPageBtn.addEventListener('click', goToPreviousPage);
nextPageBtn.addEventListener('click', goToNextPage);


// --- Initial Load ---
document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('current-year').textContent = new Date().getFullYear();
    renderStatusContent('idle', null, '', ''); // Initial idle status message
});
