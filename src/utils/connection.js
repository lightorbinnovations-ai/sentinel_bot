const https = require('https');
const http = require('http');

const MAX_RETRIES = 3;
const RETRY_DELAY = 1000;

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function makeRequest(options, retries = MAX_RETRIES) {
  return new Promise(async (resolve, reject) => {
    let lastError = null;
    
    for (let attempt = 0; attempt < retries; attempt++) {
      try {
        const result = await attemptRequest(options);
        return resolve(result);
      } catch (err) {
        lastError = err;
        if (err.errorcode === 'Not Found' || err.statusCode === 404) {
          // Don't retry on 404 - the resource doesn't exist
          return reject(err);
        }
        if (attempt < retries - 1) {
          await sleep(RETRY_DELAY * (attempt + 1));
        }
      }
    }
    
    reject(new Error(`[FATAL] All connection attempts failed. Last error: ${lastError ? lastError.message : 'Unknown'}`));
  });
}

function attemptRequest(options) {
  return new Promise((resolve, reject) => {
    const protocol = options.protocol === 'http:' ? http : https;
    
    const req = protocol.request(options, (res) => {
      let data = '';
      
      res.on('data', (chunk) => {
        data += chunk;
      });
      
      res.on('end', () => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          try {
            resolve(JSON.parse(data));
          } catch (e) {
            resolve(data);
          }
        } else if (res.statusCode === 401 || res.statusCode === 403) {
          reject({ errorcode: 'Unauthorized', statusCode: res.statusCode, message: 'Invalid token or access denied' });
        } else if (res.statusCode === 404) {
          reject({ errorcode: 'Not Found', statusCode: res.statusCode, message: 'Resource not found' });
        } else {
          reject({ errorcode: `HTTP ${res.statusCode}`, statusCode: res.statusCode, message: data });
        }
      });
    });
    
    req.on('error', (err) => {
      reject({ errorcode: 'Connection Error', message: err.message });
    });
    
    req.setTimeout(30000, () => {
      req.destroy();
      reject({ errorcode: 'Timeout', message: 'Request timed out' });
    });
    
    if (options.body) {
      req.write(typeof options.body === 'string' ? options.body : JSON.stringify(options.body));
    }
    
    req.end();
  });
}

module.exports = { makeRequest };