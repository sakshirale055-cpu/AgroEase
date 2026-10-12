document.addEventListener("DOMContentLoaded", () => {
	const header = document.querySelector(".site-header");
	const menuButton = document.querySelector(".menu-toggle");
	const navigation = document.querySelector(".site-nav");

	if (header) {
		const updateHeaderShadow = () => {
			header.classList.toggle("is-scrolled", window.scrollY > 8);
		};

		updateHeaderShadow();
		window.addEventListener("scroll", updateHeaderShadow, { passive: true });
	}

	if (menuButton && navigation) {
		const closeMenu = () => {
			menuButton.setAttribute("aria-expanded", "false");
			menuButton.setAttribute("aria-label", "Open navigation menu");
			navigation.classList.remove("is-open");
		};

		menuButton.addEventListener("click", () => {
			const isOpen = menuButton.getAttribute("aria-expanded") === "true";
			menuButton.setAttribute("aria-expanded", String(!isOpen));
			menuButton.setAttribute("aria-label", isOpen ? "Open navigation menu" : "Close navigation menu");
			navigation.classList.toggle("is-open", !isOpen);
		});

		navigation.addEventListener("click", (event) => {
			if (event.target.closest("a")) closeMenu();
		});

		document.addEventListener("click", (event) => {
			if (!header.contains(event.target)) closeMenu();
		});

		document.addEventListener("keydown", (event) => {
			if (event.key === "Escape") closeMenu();
		});

		window.addEventListener("resize", () => {
			if (window.innerWidth > 760) closeMenu();
		});
	}

});
