import Letterize from "https://cdn.skypack.dev/letterizejs@2.0.0";
import anime from "https://cdn.skypack.dev/animejs@3.2.1";


const audioContext = new (window.AudioContext || window.webkitAudioContext)();
const head = document.querySelector('.agent-head');
// get the body
const body = document.querySelector('.agent-body');
const headImage = document.querySelector('.agent-head img');
const bodyImage = document.querySelector('.agent-body img');

const agents = [
    [
        { head: '/static/img/eldrin-2.png', body: '/static/img/eldrin-1.png' },
        { head: '/static/img/head-2.png', body: '/static/img/body-2.png' },
        { head: '/static/img/head-3.png', body: '/static/img/body-3.png' },
    ]
]
let audioSource = null;
let analyser = null;
let animationId = null;
let audioBuffer = null;
let isPlaying = false;


async function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

function setupAnalyser() {
    analyser = audioContext.createAnalyser();
    analyser.fftSize = 256;
    analyser.smoothingTimeConstant = 0.8;
}

async function loadAudio(audioFile) {
    try {
        const response = await fetch(audioFile); // Replace with your audio file path
        const arrayBuffer = await response.arrayBuffer();
        return await audioContext.decodeAudioData(arrayBuffer);
    } catch (error) {
        console.error('Error loading audio:', error);
    }
}


function visualize() {
    const dataArray = new Uint8Array(analyser.frequencyBinCount);
    analyser.getByteFrequencyData(dataArray);

    // Calculate average amplitude
    const average = dataArray.reduce((acc, val) => acc + val, 0) / dataArray.length;
    // check if the audio is quiet and set rotation to 0
    // Map amplitude to rotation (-45 to 45 degrees)
    // Subtract 128 to center around 0, then scale to [-45, 45] range
    const rotation = Math.floor((((average - 128) / 128) * 35) + 35);
    const subRotation = Math.floor((((average - 128) / 128) * 15) + 15);
    // Apply rotation transform

    head.style.transform = `rotate(${rotation}deg)`;
    body.style.transform = `rotate(${subRotation}deg)`;
    // Continue animation loop
    animationId = requestAnimationFrame(visualize);
}

async function runAudio(id, audioFile) {
    let agent_id = id;
    // get a random number between 1 and 3
    let random = Math.floor(Math.random() * 2);

    // get the agent head and body
    headImage.src = agents[agent_id][0].head;
    bodyImage.src = agents[agent_id][0].body;
    // activate the model
    audioBuffer = await loadAudio(audioFile);
    // get the model head
    $("#agent-container").animate({ top: '0px' }, 500);
    setupAnalyser();
    audioSource = audioContext.createBufferSource();
    audioSource.buffer = audioBuffer;
    audioSource.connect(analyser);
    analyser.connect(audioContext.destination);

    // Start audio playback
    audioSource.start(0);
    isPlaying = true;
    // Start visualization
    visualize();


    // check when audio is done playing
    audioSource.onended = function () {
        // turn model opacity to 0

        $("#agent-container").animate({ top: '100vh' }, 500);
        head.style.transform = `rotate(0deg)`;
        body.style.transform = `rotate(0deg)`;
        isPlaying = false;
        cancelAnimationFrame(animationId);
    };
}



$(document).ready(function () {

    var socket = io();

    socket.on('start_agent', function (msg, cb) {
        console.log("Got data: " + msg)


        // move the agent up 
        $('#agent-container-' + msg.agent_id).animate({ top: '0px' }, 500);

        if (cb)
            cb();
    });

    // Updates each sentence
    socket.on('agent_audio', function (msg, cb) {
        console.log("Got data: " + msg)

        var agent_id = msg.agent_id - 1;
        var agent_audio = msg.audio;
        if (agent_id < 0) {
            agent_id = 0;
        }

        runAudio(agent_id, agent_audio);

        if (cb)
            cb();
    });

    socket.on('clear_agent', function (msg, cb) {
        console.log("Client received clear message instruction!")

        // move the agent down outside of the screen
        $('#agent-container-' + msg.agent_id).animate({ top: '100px' }, 500);

        if (cb)
            cb();
    });
});