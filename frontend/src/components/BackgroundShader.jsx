import React, { useEffect, useRef } from 'react';

const BackgroundShader = () => {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    
    const gl = canvas.getContext('webgl');
    if (!gl) return;

    const vertexShaderSource = `
      attribute vec2 position;
      void main() {
          gl_Position = vec4(position, 0.0, 1.0);
      }
    `;

    const fragmentShaderSource = `
      precision highp float;
      uniform float u_time;
      uniform vec2 u_resolution;

      void main() {
          vec2 uv = gl_FragCoord.xy / u_resolution.xy;
          
          // Create a deep obsidian/midnight blue base
          vec3 color1 = vec3(0.043, 0.059, 0.063); // #0b0f19 equivalent
          vec3 color2 = vec3(0.027, 0.035, 0.039); // Deep obsidian
          
          // Create slow, organic movement
          float noise = sin(uv.x * 2.0 + u_time * 0.2) * cos(uv.y * 2.0 + u_time * 0.3);
          noise += 0.5 * sin(uv.x * 4.0 - u_time * 0.1) * cos(uv.y * 5.0 + u_time * 0.2);
          
          // Mix colors based on noise and position
          vec3 finalColor = mix(color1, color2, uv.y + noise * 0.1);
          
          // Add a very subtle, pulsing cyan glow in the corner
          float glow = distance(uv, vec2(0.1, 0.9));
          vec3 accentColor = vec3(0.023, 0.714, 0.831); // Cyan #06b6d4
          finalColor += accentColor * (1.0 - smoothstep(0.0, 0.8, glow)) * 0.05 * (0.8 + 0.2 * sin(u_time * 0.5));
          
          gl_FragColor = vec4(finalColor, 1.0);
      }
    `;

    function createShader(gl, type, source) {
        const shader = gl.createShader(type);
        gl.shaderSource(shader, source);
        gl.compileShader(shader);
        return shader;
    }

    const vertexShader = createShader(gl, gl.VERTEX_SHADER, vertexShaderSource);
    const fragmentShader = createShader(gl, gl.FRAGMENT_SHADER, fragmentShaderSource);

    const program = gl.createProgram();
    gl.attachShader(program, vertexShader);
    gl.attachShader(program, fragmentShader);
    gl.linkProgram(program);
    gl.useProgram(program);

    const positionBuffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([
        -1.0, -1.0,
         1.0, -1.0,
        -1.0,  1.0,
        -1.0,  1.0,
         1.0, -1.0,
         1.0,  1.0
    ]), gl.STATIC_DRAW);

    const positionLocation = gl.getAttribLocation(program, 'position');
    gl.enableVertexAttribArray(positionLocation);
    gl.vertexAttribPointer(positionLocation, 2, gl.FLOAT, false, 0, 0);

    const timeLocation = gl.getUniformLocation(program, 'u_time');
    const resolutionLocation = gl.getUniformLocation(program, 'u_resolution');

    function resize() {
        if (!canvas) return;
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
        gl.viewport(0, 0, canvas.width, canvas.height);
        gl.uniform2f(resolutionLocation, canvas.width, canvas.height);
    }

    window.addEventListener('resize', resize);
    resize();

    let animationFrameId;

    function render(time) {
        time *= 0.001; // Convert to seconds
        gl.uniform1f(timeLocation, time);
        gl.drawArrays(gl.TRIANGLES, 0, 6);
        animationFrameId = requestAnimationFrame(render);
    }
    animationFrameId = requestAnimationFrame(render);

    return () => {
      window.removeEventListener('resize', resize);
      cancelAnimationFrame(animationFrameId);
    };
  }, []);

  return <canvas ref={canvasRef} id="bg-canvas" />;
};

export default BackgroundShader;
