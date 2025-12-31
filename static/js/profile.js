document.addEventListener('DOMContentLoaded', function() {
    // Handle photo upload preview
    const photoUpload = document.getElementById('photo-upload');
    if (photoUpload) {
        photoUpload.addEventListener('change', function(e) {
            if (this.files && this.files[0]) {
                const reader = new FileReader();
                reader.onload = function(e) {
                    const img = document.createElement('img');
                    img.src = e.target.result;
                    img.alt = 'Profile Photo';
                    img.id = 'profile-photo';
                    const container = document.querySelector('.profile-picture');
                    container.innerHTML = '';
                    container.appendChild(img);
                    
                    // Recreate the file input and label
                    const fileInput = document.createElement('input');
                    fileInput.type = 'file';
                    fileInput.name = 'photo';
                    fileInput.id = 'photo-upload';
                    fileInput.accept = 'image/*';
                    fileInput.style.display = 'none';
                    
                    const label = document.createElement('label');
                    label.htmlFor = 'photo-upload';
                    label.className = 'upload-btn';
                    label.textContent = 'Change Photo';
                    
                    container.appendChild(fileInput);
                    container.appendChild(label);
                    
                    // Re-attach the event listener to the new file input
                    fileInput.addEventListener('change', arguments.callee);
                };
                reader.readAsDataURL(this.files[0]);
            }
        });
    }
    
    // Handle flash messages
    const flashMessages = [];
    
    // Get flash messages from data attribute
    const flashData = document.body.getAttribute('data-flash-messages');
    if (flashData) {
        try {
            const messages = JSON.parse(flashData);
            if (Array.isArray(messages)) {
                flashMessages.push(...messages);
            }
        } catch (e) {
            console.error('Error parsing flash messages:', e);
        }
    }
    
    // Display flash messages
    if (flashMessages.length > 0) {
        const flashContainer = document.createElement('div');
        flashContainer.className = 'flash-messages';
        
        flashMessages.forEach(({ category, message }) => {
            const flashDiv = document.createElement('div');
            flashDiv.className = `flash-message ${category}`;
            flashDiv.textContent = message;
            flashContainer.prepend(flashDiv);
        });
        
        const container = document.querySelector('.container');
        if (container) {
            container.insertBefore(flashContainer, container.firstChild);
            
            // Auto-hide flash messages after 5 seconds
            setTimeout(() => {
                const messages = flashContainer.querySelectorAll('.flash-message');
                messages.forEach(msg => {
                    msg.style.opacity = '0';
                    msg.style.transition = 'opacity 0.5s';
                    setTimeout(() => msg.remove(), 500);
                });
            }, 5000);
        }
    }
});
