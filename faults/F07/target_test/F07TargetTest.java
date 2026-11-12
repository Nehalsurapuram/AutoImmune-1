package com.autoimmune.orders;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

/** F07 target test: Report retrieval endpoint serves legitimate filenames with HTTP 200. */
@SpringBootTest
@AutoConfigureMockMvc
class F07TargetTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void legitimateReportRetrievalSucceeds() throws Exception {
        mvc.perform(get("/api/orders/report").param("file", "summary.txt"))
                .andExpect(status().isOk());
    }
}
