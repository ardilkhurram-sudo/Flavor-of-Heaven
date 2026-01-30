// ============================================
// Flavor of Heaven - Main JavaScript
// ============================================

document.addEventListener('DOMContentLoaded', function() {
  // Video slider
  initVideoSlider();

  // Header scroll effect
  initHeaderScroll();

  // Mobile navigation
  initMobileNav();

  // Smooth scroll for navigation links
  initSmoothScroll();

  // Form handling
  initForms();

  // Scroll animations
  initScrollAnimations();
});

// ============================================
// Video Slider
// ============================================
function initVideoSlider() {
  const videoSlides = document.querySelectorAll('.video-slide');

  // Exit if no video slides found
  if (videoSlides.length < 2) return;

  let currentSlide = 0;
  const totalSlides = videoSlides.length;

  function switchVideo() {
    // Pause current video
    const currentVideo = videoSlides[currentSlide].querySelector('video');
    currentVideo.pause();
    videoSlides[currentSlide].classList.remove('active');

    // Move to next slide
    currentSlide = (currentSlide + 1) % totalSlides;

    // Play next video
    const nextVideo = videoSlides[currentSlide].querySelector('video');
    videoSlides[currentSlide].classList.add('active');
    nextVideo.currentTime = 0;
    nextVideo.play();
  }

  // Switch videos every 5 seconds
  setInterval(switchVideo, 5000);
}

// ============================================
// Header Scroll Effect
// ============================================
function initHeaderScroll() {
  const header = document.querySelector('.header');

  function updateHeader() {
    if (window.scrollY > 100) {
      header.classList.add('scrolled');
    } else {
      header.classList.remove('scrolled');
    }
  }

  window.addEventListener('scroll', updateHeader);
  updateHeader(); // Check initial state
}

// ============================================
// Mobile Navigation
// ============================================
function initMobileNav() {
  const navToggle = document.querySelector('.nav-toggle');
  const navMenu = document.querySelector('.nav-menu');
  const navLinks = document.querySelectorAll('.nav-link');

  if (!navToggle || !navMenu) return;

  navToggle.addEventListener('click', function() {
    navMenu.classList.toggle('active');
    navToggle.classList.toggle('active');
    document.body.style.overflow = navMenu.classList.contains('active') ? 'hidden' : '';
  });

  // Close menu when clicking a link
  navLinks.forEach(link => {
    link.addEventListener('click', function() {
      navMenu.classList.remove('active');
      navToggle.classList.remove('active');
      document.body.style.overflow = '';
    });
  });

  // Close menu when clicking outside
  document.addEventListener('click', function(e) {
    if (!navMenu.contains(e.target) && !navToggle.contains(e.target)) {
      navMenu.classList.remove('active');
      navToggle.classList.remove('active');
      document.body.style.overflow = '';
    }
  });
}

// ============================================
// Smooth Scroll
// ============================================
function initSmoothScroll() {
  const links = document.querySelectorAll('a[href^="#"]');

  links.forEach(link => {
    link.addEventListener('click', function(e) {
      const href = this.getAttribute('href');
      if (href === '#') return;

      const target = document.querySelector(href);
      if (!target) return;

      e.preventDefault();

      const headerHeight = document.querySelector('.header').offsetHeight;
      const targetPosition = target.getBoundingClientRect().top + window.scrollY - headerHeight;

      window.scrollTo({
        top: targetPosition,
        behavior: 'smooth'
      });

      // Update active nav link
      updateActiveNavLink(href);
    });
  });

  // Update active link on scroll
  window.addEventListener('scroll', debounce(function() {
    const sections = document.querySelectorAll('section[id]');
    const scrollPos = window.scrollY + 200;

    sections.forEach(section => {
      const top = section.offsetTop;
      const height = section.offsetHeight;
      const id = section.getAttribute('id');

      if (scrollPos >= top && scrollPos < top + height) {
        updateActiveNavLink('#' + id);
      }
    });
  }, 100));
}

function updateActiveNavLink(href) {
  const navLinks = document.querySelectorAll('.nav-link');
  navLinks.forEach(link => {
    link.classList.remove('active');
    if (link.getAttribute('href') === href) {
      link.classList.add('active');
    }
  });
}

// ============================================
// Form Handling
// ============================================
function initForms() {
  // Newsletter form
  const newsletterForm = document.querySelector('.newsletter-form');
  if (newsletterForm) {
    newsletterForm.addEventListener('submit', function(e) {
      e.preventDefault();

      const email = this.querySelector('input[type="email"]').value;

      if (!email) {
        showNotification('Please enter your email address.', 'error');
        return;
      }

      // Simulate subscription
      const submitBtn = this.querySelector('button[type="submit"]');
      const originalText = submitBtn.textContent;
      submitBtn.textContent = 'Subscribing...';
      submitBtn.disabled = true;

      setTimeout(() => {
        showNotification('Thank you for subscribing! Check your inbox for exclusive offers.', 'success');
        this.reset();
        submitBtn.textContent = originalText;
        submitBtn.disabled = false;
      }, 1000);
    });
  }
}

// ============================================
// Notification System
// ============================================
function showNotification(message, type = 'info') {
  // Remove existing notifications
  const existing = document.querySelector('.notification');
  if (existing) existing.remove();

  // Create notification element
  const notification = document.createElement('div');
  notification.className = `notification notification-${type}`;
  notification.innerHTML = `
    <span>${message}</span>
    <button class="notification-close">&times;</button>
  `;

  // Add styles
  Object.assign(notification.style, {
    position: 'fixed',
    top: '100px',
    right: '20px',
    maxWidth: '400px',
    padding: '16px 20px',
    borderRadius: '8px',
    backgroundColor: type === 'success' ? '#16a34a' : type === 'error' ? '#dc2626' : '#3b82f6',
    color: 'white',
    boxShadow: '0 10px 25px rgba(0, 0, 0, 0.2)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: '12px',
    zIndex: '9999',
    animation: 'slideIn 0.3s ease'
  });

  // Add animation keyframes if not exists
  if (!document.querySelector('#notification-styles')) {
    const style = document.createElement('style');
    style.id = 'notification-styles';
    style.textContent = `
      @keyframes slideIn {
        from { transform: translateX(100%); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
      }
      @keyframes slideOut {
        from { transform: translateX(0); opacity: 1; }
        to { transform: translateX(100%); opacity: 0; }
      }
      .notification-close {
        background: none;
        border: none;
        color: white;
        font-size: 20px;
        cursor: pointer;
        padding: 0;
        line-height: 1;
        opacity: 0.8;
      }
      .notification-close:hover {
        opacity: 1;
      }
    `;
    document.head.appendChild(style);
  }

  document.body.appendChild(notification);

  // Close button
  const closeBtn = notification.querySelector('.notification-close');
  closeBtn.addEventListener('click', () => removeNotification(notification));

  // Auto remove after 5 seconds
  setTimeout(() => removeNotification(notification), 5000);
}

function removeNotification(notification) {
  if (!notification) return;
  notification.style.animation = 'slideOut 0.3s ease';
  setTimeout(() => notification.remove(), 300);
}

// ============================================
// Scroll Animations
// ============================================
function initScrollAnimations() {
  const animatedElements = document.querySelectorAll(
    '.about-content, .about-images, .menu-card, .special-card, .testimonial-card, .gallery-item'
  );

  if (!animatedElements.length) return;

  // Add initial styles
  const style = document.createElement('style');
  style.textContent = `
    .animate-on-scroll {
      opacity: 0;
      transform: translateY(30px);
      transition: opacity 0.6s ease, transform 0.6s ease;
    }
    .animate-on-scroll.animated {
      opacity: 1;
      transform: translateY(0);
    }
  `;
  document.head.appendChild(style);

  animatedElements.forEach((el, index) => {
    el.classList.add('animate-on-scroll');
    el.style.transitionDelay = `${(index % 4) * 0.1}s`;
  });

  // Intersection Observer
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('animated');
        observer.unobserve(entry.target);
      }
    });
  }, {
    threshold: 0.1,
    rootMargin: '0px 0px -50px 0px'
  });

  animatedElements.forEach(el => observer.observe(el));
}

// ============================================
// Utility Functions
// ============================================
function debounce(func, wait) {
  let timeout;
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
}
