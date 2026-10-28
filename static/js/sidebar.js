(() => {
  const storageRead = (key) => {
    try {
      return window.localStorage.getItem(key);
    } catch (error) {
      return null;
    }
  };
  const storageWrite = (key, value) => {
    try {
      window.localStorage.setItem(key, value);
    } catch (error) {
      return false;
    }
    return true;
  };

  document.querySelectorAll('[data-role-sidebar]').forEach((sidebar) => {
    const layout = sidebar.closest('.dashboard-layout');
    const panel = sidebar.querySelector('.role-sidebar-scroll');
    const openButton = layout.querySelector('[data-sidebar-open]');
    const collapseButton = sidebar.querySelector('[data-sidebar-collapse]');
    const closeButton = sidebar.querySelector('[data-sidebar-close]');
    const backdrop = layout.querySelector('[data-sidebar-backdrop]');
    const sectionKey = 'sgr.sidebar.sections.v1';
    const collapsedKey = 'sgr.sidebar.collapsed.v1';
    const sections = [...sidebar.querySelectorAll('[data-sidebar-section]')];
    let savedSections = {};
    let mobileWasOpen = false;

    try {
      const parsed = JSON.parse(storageRead(sectionKey) || '{}');
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        savedSections = parsed;
      }
    } catch (error) {
      savedSections = {};
    }

    sections.forEach((section) => {
      const key = section.dataset.sectionKey;
      if (section.dataset.current === 'true') {
        section.open = true;
      } else if (typeof savedSections[key] === 'boolean') {
        section.open = savedSections[key];
      }
      section.addEventListener('toggle', () => {
        savedSections[key] = section.open;
        storageWrite(sectionKey, JSON.stringify(savedSections));
      });
    });

    const setCollapsed = (collapsed, persist = true) => {
      layout.classList.toggle('sidebar-collapsed', collapsed);
      collapseButton.setAttribute('aria-expanded', String(!collapsed));
      collapseButton.setAttribute(
        'aria-label',
        collapsed ? 'Expandir menú' : 'Contraer menú',
      );
      collapseButton.title = collapsed ? 'Expandir menú' : 'Contraer menú';
      collapseButton.querySelector('span').textContent = collapsed ? '⇥' : '⇤';
      if (persist) {
        storageWrite(collapsedKey, String(collapsed));
      }
    };

    setCollapsed(storageRead(collapsedKey) === 'true', false);
    collapseButton.addEventListener('click', () => {
      setCollapsed(!layout.classList.contains('sidebar-collapsed'));
    });

    const closeMobileMenu = (restoreFocus = false) => {
      sidebar.classList.remove('is-mobile-open');
      backdrop.hidden = true;
      document.body.classList.remove('sidebar-open');
      openButton.setAttribute('aria-expanded', 'false');
      if (restoreFocus) {
        openButton.focus();
      }
      mobileWasOpen = false;
    };

    openButton.addEventListener('click', () => {
      sidebar.classList.add('is-mobile-open');
      backdrop.hidden = false;
      document.body.classList.add('sidebar-open');
      openButton.setAttribute('aria-expanded', 'true');
      mobileWasOpen = true;
      const activeLink = sidebar.querySelector('.sidebar-link.active');
      (activeLink || sidebar.querySelector('.sidebar-section-summary')).focus();
    });
    closeButton.addEventListener('click', () => closeMobileMenu(true));
    backdrop.addEventListener('click', () => closeMobileMenu(true));
    panel.querySelectorAll('a.sidebar-link').forEach((link) => {
      link.addEventListener('click', () => {
        if (window.matchMedia('(max-width: 900px)').matches) {
          closeMobileMenu();
        }
      });
    });

    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && mobileWasOpen) {
        closeMobileMenu(true);
      }
    });
    window.addEventListener('resize', () => {
      if (!window.matchMedia('(max-width: 900px)').matches && mobileWasOpen) {
        closeMobileMenu();
      }
    });
  });
})();
