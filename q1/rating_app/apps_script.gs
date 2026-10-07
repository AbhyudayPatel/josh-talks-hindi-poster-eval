/**
 * OPTIONAL backend: collects ratings from rate.html into a Google Sheet.
 * 1. Create a Google Sheet -> Extensions -> Apps Script -> paste this file.
 * 2. Deploy -> New deployment -> Web app -> Execute as: Me, Access: Anyone.
 * 3. Copy the /exec URL and rebuild the app:  python build_rating_app.py --endpoint "<URL>"
 * Participants can always also download their CSV (fallback / consent proof).
 */
function doPost(e) {
  const rows = JSON.parse(e.postData.contents);
  const sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('ratings') ||
             SpreadsheetApp.getActiveSpreadsheet().insertSheet('ratings');
  const header = Object.keys(rows[0]);
  if (sh.getLastRow() === 0) sh.appendRow(header);
  rows.forEach(r => sh.appendRow(header.map(k => r[k])));
  return ContentService.createTextOutput('ok');
}
