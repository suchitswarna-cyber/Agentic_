// A short quote at the bottom of the page, different each time SSC opens.
(function () {
  const QUOTES = [
    ["Arise, awake, and stop not till the goal is reached.", "Swami Vivekananda"],
    ["Dream, dream, dream. Dreams transform into thoughts and thoughts result in action.", "A. P. J. Abdul Kalam"],
    ["The journey of a thousand miles begins with one step.", "Lao Tzu"],
    ["Well done is better than well said.", "Benjamin Franklin"],
    ["Energy and persistence conquer all things.", "Benjamin Franklin"],
    ["Do what you can, with what you have, where you are.", "Theodore Roosevelt"],
    ["The best way out is always through.", "Robert Frost"],
    ["Act as if what you do makes a difference. It does.", "William James"],
    ["It always seems impossible until it's done.", "Nelson Mandela"],
    ["Knowledge is power.", "Francis Bacon"],
    ["Fortune favours the bold.", "Virgil"],
    ["Well begun is half done.", "Aristotle"],
    ["Nothing will work unless you do.", "Maya Angelou"],
    ["The secret of getting ahead is getting started.", "Mark Twain"],
    ["Patience is bitter, but its fruit is sweet.", "Jean-Jacques Rousseau"],
    ["Whatever you are, be a good one.", "Abraham Lincoln"],
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
