// Language Switcher Function
function setLanguage(languageCode) {
    document.getElementById("languageInput").value = languageCode;
    document.getElementById("languageForm").submit();
}

// Navigation Item Hover Effects
document.addEventListener('DOMContentLoaded', function() {
    // Apply gradient hover effects to navigation items
    const navItems = document.querySelectorAll('.nav-item-hover');
    
    navItems.forEach(item => {
        item.addEventListener('mouseenter', function() {
            this.style.background = 'linear-gradient(90deg, rgba(0, 225, 255, 0.15) 0%, rgba(0, 225, 255, 0.05) 100%)';
            this.style.boxShadow = '0 2px 10px rgba(0, 225, 255, 0.2)';
        });
        
        item.addEventListener('mouseleave', function() {
            this.style.background = 'linear-gradient(90deg, transparent 0%, transparent 100%)';
            this.style.boxShadow = 'none';
        });
    });

    // Apply red gradient hover for logout
    const logoutBtn = document.querySelector('.logout-hover');
    if (logoutBtn) {
        logoutBtn.addEventListener('mouseenter', function() {
            this.style.background = 'linear-gradient(90deg, rgba(239, 68, 68, 0.15) 0%, rgba(239, 68, 68, 0.05) 100%)';
            this.style.boxShadow = '0 2px 10px rgba(239, 68, 68, 0.2)';
        });
        
        logoutBtn.addEventListener('mouseleave', function() {
            this.style.background = 'linear-gradient(90deg, transparent 0%, transparent 100%)';
            this.style.boxShadow = 'none';
        });
    }
});
