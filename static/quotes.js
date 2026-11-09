// A short motivational quote under the message box when SSC opens.
// It goes away once the chat starts (see addMessage in index.html).
(function () {
  const QUOTES = [
    ["Arise, awake, and stop not till the goal is reached.", "Swami Vivekananda"],
    ["Dream, dream, dream. Dreams transform into thoughts and thoughts result in action.", "A. P. J. Abdul Kalam"],
    ["If you want to shine like a sun, first burn like a sun.", "A. P. J. Abdul Kalam"],
    ["The secret of getting ahead is getting started.", "Mark Twain"],
    ["It always seems impossible until it's done.", "Nelson Mandela"],
    ["Believe you can and you're halfway there.", "Theodore Roosevelt"],
    ["Do what you can, with what you have, where you are.", "Theodore Roosevelt"],
    ["It does not matter how slowly you go as long as you do not stop.", "Confucius"],
    ["Act as if what you do makes a difference. It does.", "William James"],
    ["Energy and persistence conquer all things.", "Benjamin Franklin"],
    ["Nothing will work unless you do.", "Maya Angelou"],
    ["The best way out is always through.", "Robert Frost"],
    ["Hard work beats talent when talent doesn't work hard.", "Tim Notke"],
    ["The journey of a thousand miles begins with one step.", "Lao Tzu"],
    ["Well begun is half done.", "Aristotle"],
    ["Fortune favours the bold.", "Virgil"],
  ];
  const el = document.getElementById("quote");
  if (!el) return;
  let last = -1;
  try { last = Number(localStorage.getItem("ssc.quote") ?? -1); } catch {}
  let i = Math.floor(Math.random() * QUOTES.length);
  if (i === last) i = (i + 1) % QUOTES.length;  // never the same one twice in a row
  try { localStorage.setItem("ssc.quote", String(i)); } catch {}
  const [text, author] = QUOTES[i];
  el.innerHTML = '<span class="q-text"></span> <span class="q-author"></span>';
  el.querySelector(".q-text").textContent = `“${text}”`;
  el.querySelector(".q-author").textContent = `— ${author}`;
})();
