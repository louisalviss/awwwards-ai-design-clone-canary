(() => {
  const root = document.documentElement;
  const update = () => root.style.setProperty('--scroll-y', String(window.scrollY));
  update();
  addEventListener('scroll', update, {passive:true});
})();
