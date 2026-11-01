(() => {
  const normalize = (value) => value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLocaleLowerCase('es');

  const highlight = (element, terms) => {
    const text = element.dataset.originalText || element.textContent;
    element.dataset.originalText = text;
    const characters = Array.from(text);
    let normalizedText = '';
    const positions = [];
    let originalOffset = 0;

    characters.forEach((character) => {
      const start = originalOffset;
      const end = start + character.length;
      const normalizedCharacter = normalize(character);
      normalizedText += normalizedCharacter;
      for (let offset = 0; offset < normalizedCharacter.length; offset += 1) {
        positions.push({start, end});
      }
      originalOffset = end;
    });

    const ranges = [];
    terms.forEach((term) => {
      let startAt = 0;
      let index = normalizedText.indexOf(term, startAt);
      while (index !== -1) {
        const first = positions[index];
        const last = positions[index + term.length - 1];
        if (first && last) {
          ranges.push([first.start, last.end]);
        }
        startAt = index + term.length;
        index = normalizedText.indexOf(term, startAt);
      }
    });

    ranges.sort((left, right) => left[0] - right[0]);
    const merged = [];
    ranges.forEach(([start, end]) => {
      const previous = merged[merged.length - 1];
      if (previous && start <= previous[1]) {
        previous[1] = Math.max(previous[1], end);
      } else {
        merged.push([start, end]);
      }
    });

    element.replaceChildren();
    let cursor = 0;
    merged.forEach(([start, end]) => {
      if (start > cursor) {
        element.append(document.createTextNode(text.slice(cursor, start)));
      }
      const mark = document.createElement('mark');
      mark.textContent = text.slice(start, end);
      element.append(mark);
      cursor = end;
    });
    if (cursor < text.length) {
      element.append(document.createTextNode(text.slice(cursor)));
    }
    if (!merged.length) {
      element.textContent = text;
    }
  };

  document.querySelectorAll('[data-permission-selector]').forEach((selector) => {
    const search = selector.querySelector('[data-permission-search]');
    const results = selector.querySelector('[data-permission-results]');
    const onlySelected = selector.querySelector('[data-permission-only-selected]');
    const chips = selector.querySelector('[data-permission-chips]');
    const emptySelection = selector.querySelector('[data-permission-empty]');
    const noResults = selector.querySelector('[data-permission-no-results]');
    const groups = [...selector.querySelectorAll('[data-permission-module]')];
    const options = [...selector.querySelectorAll('[data-permission-option]')];
    const checkboxes = options.map((option) => option.querySelector('input[type="checkbox"]'));

    const update = () => {
      const terms = normalize(search.value).trim().split(/\s+/).filter(Boolean);
      let resultCount = 0;

      options.forEach((option) => {
        const checkbox = option.querySelector('input[type="checkbox"]');
        const name = option.querySelector('[data-permission-name]');
        const description = option.querySelector('[data-permission-description]');
        const searchable = normalize([
          name.dataset.originalText || name.textContent,
          description.dataset.originalText || description.textContent,
          option.dataset.module,
        ].join(' '));
        const matches = terms.every((term) => searchable.includes(term));
        const visible = matches && (!onlySelected.checked || checkbox.checked);
        option.hidden = !visible;
        if (visible) {
          resultCount += 1;
        }
        highlight(name, terms);
        highlight(description, terms);
      });

      groups.forEach((group) => {
        const groupOptions = [...group.querySelectorAll('[data-permission-option]')];
        const visibleCount = groupOptions.filter((option) => !option.hidden).length;
        group.hidden = visibleCount === 0;
        if (terms.length && visibleCount) {
          group.open = true;
        }
        const selectedCount = groupOptions.filter(
          (option) => option.querySelector('input[type="checkbox"]').checked,
        ).length;
        const counter = group.querySelector('[data-module-count]');
        counter.dataset.selected = selectedCount;
        counter.textContent = `${selectedCount} de ${counter.dataset.total} seleccionados`;
        highlight(group.querySelector('[data-module-title]'), terms);
      });

      results.textContent = `${resultCount} ${resultCount === 1 ? 'resultado' : 'resultados'}`;
      noResults.hidden = resultCount !== 0;
      chips.replaceChildren();
      let selectedCount = 0;
      checkboxes.forEach((checkbox) => {
        if (!checkbox.checked) {
          return;
        }
        selectedCount += 1;
        const option = checkbox.closest('[data-permission-option]');
        const name = option.querySelector('[data-permission-name]').dataset.originalText
          || option.querySelector('[data-permission-name]').textContent;
        const chip = document.createElement('span');
        chip.className = 'permission-chip';
        const label = document.createElement('span');
        label.textContent = name;
        const remove = document.createElement('button');
        remove.type = 'button';
        remove.textContent = '×';
        remove.setAttribute('aria-label', `Quitar permiso: ${name}`);
        remove.addEventListener('click', () => {
          checkbox.checked = false;
          update();
        });
        chip.append(label, remove);
        chips.append(chip);
      });
      emptySelection.hidden = selectedCount > 0;
    };

    checkboxes.forEach((checkbox) => checkbox.addEventListener('change', update));
    search.addEventListener('input', update);
    onlySelected.addEventListener('change', update);

    selector.querySelectorAll('[data-module-select]').forEach((button) => {
      button.addEventListener('click', () => {
        button.closest('[data-permission-module]')
          .querySelectorAll('[data-permission-option] input[type="checkbox"]')
          .forEach((checkbox) => {
            if (!checkbox.disabled) {
              checkbox.checked = true;
            }
          });
        update();
      });
    });
    selector.querySelectorAll('[data-module-clear]').forEach((button) => {
      button.addEventListener('click', () => {
        button.closest('[data-permission-module]')
          .querySelectorAll('[data-permission-option] input[type="checkbox"]')
          .forEach((checkbox) => {
            if (!checkbox.disabled) {
              checkbox.checked = false;
            }
          });
        update();
      });
    });
    selector.querySelector('[data-permission-clear-all]').addEventListener('click', () => {
      checkboxes.forEach((checkbox) => {
        if (!checkbox.disabled) {
          checkbox.checked = false;
        }
      });
      update();
    });

    update();
  });
})();
