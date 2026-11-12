package com.autoimmune.orders;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.io.File;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.stream.Stream;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

/**
 * F03 Target Test:
 * Verifies receipt export succeeds with HTTP 200 AND releases the OS file descriptor / file lock.
 */
@SpringBootTest
@AutoConfigureMockMvc
class F03TargetTest {

    @Autowired
    private MockMvc mvc;

    private File receiptFile;

    @BeforeEach
    void setup() {
        receiptFile = new File(System.getProperty("java.io.tmpdir"), "order-receipt-1.dat");
        if (receiptFile.exists()) {
            receiptFile.delete();
        }
    }

    @AfterEach
    void cleanup() {
        if (receiptFile != null && receiptFile.exists()) {
            receiptFile.delete();
        }
    }

    @Test
    void receiptExportSucceedsAndReleasesResource() throws Exception {
        mvc.perform(get("/api/orders/1/receipt"))
                .andExpect(status().isOk())
                .andExpect(content().string("RECEIPT-1"));

        // Verify resource release
        assertResourceReleased(receiptFile);
    }

    private void assertResourceReleased(File file) throws Exception {
        // 1. Linux procfs check if running on Linux / Docker
        Path procFd = Paths.get("/proc/self/fd");
        if (Files.exists(procFd)) {
            try (Stream<Path> fds = Files.list(procFd)) {
                boolean leaked = fds.anyMatch(fd -> {
                    try {
                        return Files.readSymbolicLink(fd).toString().contains(file.getName());
                    } catch (Exception e) {
                        return false;
                    }
                });
                assertFalse(leaked, "OS file descriptor leaked for " + file.getName() + " in /proc/self/fd");
            }
        }

        // 2. Cross-platform / Windows OS lock check
        // If FileInputStream is unclosed, delete() fails on Windows with sharing violation
        assertTrue(file.delete(), "Resource lock detected: failed to delete file while handle held open");
    }
}
