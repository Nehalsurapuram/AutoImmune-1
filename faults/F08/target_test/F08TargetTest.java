package com.autoimmune.orders;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

/** F08 target test: Single-threaded repository lookup returns order 1 successfully. */
@SpringBootTest
@AutoConfigureMockMvc
class F08TargetTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void singleThreadedOrderLookupSucceeds() throws Exception {
        mvc.perform(get("/api/orders/1/total"))
                .andExpect(status().isOk());
    }
}
