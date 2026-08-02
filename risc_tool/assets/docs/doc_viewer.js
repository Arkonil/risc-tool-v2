export default function (component) {
  const { data, setStateValue, parentElement } = component;

  // Guard against uninitialized state
  if (!data) return;
  const { pages, activeIndex } = data;

  // Apply Streamlit theme dynamically
  const themeBase = data?.theme || "light";

  // Create the main container if it doesn't exist
  let container = parentElement.querySelector("#doc-container");
  if (!container) {
    container = document.createElement("div");
    container.id = "doc-container";
    parentElement.appendChild(container);

    const contentArea = document.createElement("div");
    contentArea.id = "doc-content";
    container.appendChild(contentArea);

    const navigator = document.createElement("nav");
    navigator.id = "doc-navigator";
    container.appendChild(navigator);
  }

  const contentArea = container.querySelector("#doc-content");
  const navigator = container.querySelector("#doc-navigator");

  // Render the navigator
  navigator.innerHTML = "";

  // Add static Contents header
  const navHeader = document.createElement("div");
  navHeader.textContent = "Contents";
  navHeader.className = "nav-header";
  navigator.appendChild(navHeader);

  const navList = document.createElement("ul");
  pages.forEach((page, index) => {
    const item = document.createElement("li");
    item.textContent = page.title;
    item.className = "nav-item" + (index === activeIndex ? " active" : "");
    item.onclick = () => {
      setStateValue("activeIndex", index);
    };
    navList.appendChild(item);
  });
  navigator.appendChild(navList);

  // Render the content
  const currentPage = pages[activeIndex];
  if (currentPage && currentPage.content) {
    // Use ShadowRoot for content to isolate GFM styles
    let shadow = contentArea.shadowRoot;
    if (!shadow) {
      shadow = contentArea.attachShadow({ mode: "open" });
    }

    // Inject content
    shadow.innerHTML = currentPage.content;

    // Apply theme to the container inside shadow root
    const shadowContent = shadow.querySelector(".markdown-body");
    if (shadowContent) {
      shadowContent.setAttribute("data-theme", themeBase);

      // ELIMINATE TOP SPACE: ensure first heading has no margin
      const firstHeading = shadowContent.querySelector(
        "h1, h2, h3, h4, h5, h6",
      );
      if (firstHeading) {
        firstHeading.style.marginTop = "0";
        firstHeading.style.paddingTop = "0";
      }
    }
  }
}
